"""Generate the legacy Tableau workbook (.twbx) from the pipeline's CSV extract.

    python tableau/build_workbook.py            # writes tableau/ServiceDesk_Legacy.twbx

The workbook is plain Tableau XML (.twb) packaged together with
exports/tableau/incidents.csv, so it opens in Tableau Desktop or the free
Tableau Public app without any database connection.

Contents
  * 8 calculated fields - the KPI definitions of the legacy dashboard
  * 6 KPI tiles, 5 charts, 1 dashboard ('Service Desk Overview (legacy)')
  * sheet 'KPI Validation': week x KPI crosstab. Export it (Worksheet >
    Export > Crosstab, CSV) to validation/tableau_export.csv and the pipeline
    compares the real Tableau numbers with the new stack.

The calculated fields below are the 'legacy logic' that pipeline/validation.py
re-implements in pandas - keep the two in sync.
"""

from __future__ import annotations

import csv
import zipfile
from pathlib import Path
from xml.sax.saxutils import escape, quoteattr

ROOT = Path(__file__).resolve().parents[1]
EXTRACT = ROOT / "exports" / "tableau" / "incidents.csv"
OUT = ROOT / "tableau" / "ServiceDesk_Legacy.twbx"
TWB_NAME = "ServiceDesk_Legacy.twb"
DATA_DIR = "Data/tableau"           # relative path inside the .twbx package

DS = "federated.0servicedesk01"     # internal datasource name
CONN = "textscan.0servicedesk01"
DS_CAPTION = "incidents"

# Column types in incidents.csv (Tableau datatype names)
COLUMN_TYPES = {
    "incident_number": "string", "opened_at": "datetime", "opened_date": "date", "opened_week_start": "date",
    "opened_month": "string", "opened_weekday": "string", "resolved_at": "datetime", "closed_at": "datetime",
    "contact_type": "string", "category": "string", "subcategory": "string", "priority": "string",
    "priority_code": "integer", "assignment_group": "string", "knowledge_used": "integer", "made_sla": "integer",
    "is_resolved": "integer", "is_first_contact_resolution": "integer", "is_reopened": "integer",
    "reassignment_count": "integer", "reassignment_bucket": "string", "reopen_count": "integer",
    "resolution_hours": "real", "close_hours": "real", "awaiting_user_hours": "real", "category_top10": "string",
}
REMOTE_TYPE = {"string": 129, "integer": 20, "real": 5, "date": 133, "datetime": 135}
AGGREGATION = {"string": "Count", "integer": "Sum", "real": "Sum", "date": "Year", "datetime": "Year"}

# KPI calculated fields: (internal id, caption, formula, datatype, number format)
# Captions must match pipeline/validation.py KPIS so a crosstab export can be read back.
CALCS = [
    ("Calculation_9700000000000000001", "Incidents", "COUNT([incident_number])", "integer", "n#,##0;-#,##0"),
    ("Calculation_9700000000000000002", "Resolved incidents", "SUM([is_resolved])", "integer", "n#,##0;-#,##0"),
    ("Calculation_9700000000000000003", "Median resolution (h)", "MEDIAN([resolution_hours])", "real",
     "n#,##0.00;-#,##0.00"),
    ("Calculation_9700000000000000004", "SLA met (%)", "100 * SUM([made_sla]) / COUNT([incident_number])", "real",
     "n#,##0.00;-#,##0.00"),
    ("Calculation_9700000000000000005", "First-contact resolution (%)",
     "100 * SUM([is_first_contact_resolution]) / COUNT([incident_number])", "real", "n#,##0.00;-#,##0.00"),
    ("Calculation_9700000000000000006", "Knowledge used (%)", "100 * SUM([knowledge_used]) / COUNT([incident_number])",
     "real", "n#,##0.00;-#,##0.00"),
    ("Calculation_9700000000000000007", "Reopen rate (%)", "100 * SUM([is_reopened]) / COUNT([incident_number])",
     "real", "n#,##0.00;-#,##0.00"),
    ("Calculation_9700000000000000008", "Avg reassignments", "AVG([reassignment_count])", "real",
     "n#,##0.00;-#,##0.00"),
]
CALC_BY_CAPTION = {c[1]: c for c in CALCS}
BASE_FIELDS_IN_CALCS = ["incident_number", "is_resolved", "resolution_hours", "made_sla",
                        "is_first_contact_resolution", "knowledge_used", "is_reopened", "reassignment_count"]


def q(value) -> str:
    return quoteattr(str(value))


# --------------------------------------------------------------------------
# Datasource
# --------------------------------------------------------------------------
def datasource_xml(header: list[str]) -> str:
    cols = "\n".join(
        f"            <column datatype={q(COLUMN_TYPES[c])} name={q(c)} ordinal='{i}' />"
        for i, c in enumerate(header))
    records = "\n".join(f"""          <metadata-record class='column'>
            <remote-name>{escape(c)}</remote-name>
            <remote-type>{REMOTE_TYPE[COLUMN_TYPES[c]]}</remote-type>
            <local-name>[{escape(c)}]</local-name>
            <parent-name>[incidents.csv]</parent-name>
            <remote-alias>{escape(c)}</remote-alias>
            <ordinal>{i}</ordinal>
            <local-type>{COLUMN_TYPES[c]}</local-type>
            <aggregation>{AGGREGATION[COLUMN_TYPES[c]]}</aggregation>
            <contains-null>true</contains-null>
          </metadata-record>""" for i, c in enumerate(header))
    calcs = "\n".join(f"""      <column caption={q(cap)} datatype={q(dt)} default-format={q(fmt)} name='[{cid}]' role='measure' type='quantitative'>
        <calculation class='tableau' formula={q(formula)} />
      </column>""" for cid, cap, formula, dt, fmt in CALCS)
    return f"""  <datasources>
    <datasource caption={q(DS_CAPTION)} inline='true' name={q(DS)} version='18.1'>
      <connection class='federated'>
        <named-connections>
          <named-connection caption={q(DS_CAPTION)} name={q(CONN)}>
            <connection class='textscan' directory={q(DATA_DIR)} filename='incidents.csv' password='' server='' />
          </named-connection>
        </named-connections>
        <relation connection={q(CONN)} name='incidents.csv' table='[incidents#csv]' type='table'>
          <columns character-set='UTF-8' header='yes' locale='en_US' separator=','>
{cols}
          </columns>
        </relation>
        <metadata-records>
{records}
        </metadata-records>
      </connection>
      <aliases enabled='yes' />
{calcs}
      <layout dim-ordering='alphabetic' dim-percentage='0.5' measure-ordering='alphabetic' measure-percentage='0.4' show-structure='true' />
    </datasource>
  </datasources>"""


# --------------------------------------------------------------------------
# Worksheets
# --------------------------------------------------------------------------
def base_col(name: str) -> str:
    dt = COLUMN_TYPES[name]
    role = "measure" if dt in ("integer", "real") else "dimension"
    typ = "quantitative" if role == "measure" else ("ordinal" if dt in ("date", "datetime") else "nominal")
    return f"            <column datatype={q(dt)} name='[{name}]' role={q(role)} type={q(typ)} />"


def calc_col(caption: str) -> str:
    cid, cap, formula, dt, fmt = CALC_BY_CAPTION[caption]
    return (f"            <column caption={q(cap)} datatype={q(dt)} default-format={q(fmt)} name='[{cid}]' "
            f"role='measure' type='quantitative'>\n"
            f"              <calculation class='tableau' formula={q(formula)} />\n"
            f"            </column>")


def calc_ref(caption: str) -> str:
    return f"[{DS}].[usr:{CALC_BY_CAPTION[caption][0]}:qk]"


def calc_instance(caption: str) -> str:
    cid = CALC_BY_CAPTION[caption][0]
    return (f"            <column-instance column='[{cid}]' derivation='User' name='[usr:{cid}:qk]' "
            f"pivot='key' type='quantitative' />")


def dim_instance(name: str, continuous: bool = False) -> tuple[str, str]:
    """Return (column-instance xml, shelf reference) for an unaggregated dimension."""
    dt = COLUMN_TYPES[name]
    if continuous:
        suffix, typ = "qk", "quantitative"
    elif dt in ("date", "datetime"):
        suffix, typ = "ok", "ordinal"
    else:
        suffix, typ = "nk", "nominal"
    inst = f"none:{name}:{suffix}"
    xml = (f"            <column-instance column='[{name}]' derivation='None' name='[{inst}]' "
           f"pivot='key' type={q(typ)} />")
    return xml, f"[{DS}].[{inst}]"


def worksheet(name: str, measures: list[str], rows: str = "", cols: str = "", mark: str = "Automatic",
              dims: list[tuple[str, bool]] = (), text_measure: str | None = None,
              measure_names: bool = False) -> str:
    deps = [base_col(f) for f in BASE_FIELDS_IN_CALCS]
    deps += [calc_col(m) for m in measures]
    dim_refs = {}
    for dname, continuous in dims:
        if dname not in BASE_FIELDS_IN_CALCS:
            deps.append(base_col(dname))
        inst_xml, ref = dim_instance(dname, continuous)
        deps.append(inst_xml)
        dim_refs[dname] = ref
    deps += [calc_instance(m) for m in measures]

    view_extra = ""
    encodings = ""
    if measure_names:
        members = "\n".join(
            f"              <groupfilter function='member' level='[:Measure Names]' member={q(chr(34) + calc_ref(m) + chr(34))} />"
            for m in measures)
        view_extra = f"""          <filter class='categorical' column='[{DS}].[:Measure Names]'>
            <groupfilter function='union' user:op='manual'>
{members}
            </groupfilter>
          </filter>
          <slices>
            <column>[{DS}].[:Measure Names]</column>
          </slices>
"""
        encodings = f"""            <encodings>
              <text column='[{DS}].[Multiple Values]' />
            </encodings>
"""
    elif text_measure:
        encodings = f"""            <encodings>
              <text column={q(calc_ref(text_measure))} />
            </encodings>
"""
    rows = rows.format(**dim_refs, **{f"m{i}": calc_ref(m) for i, m in enumerate(measures)})
    cols = cols.format(**dim_refs, **{f"m{i}": calc_ref(m) for i, m in enumerate(measures)})
    deps_xml = "\n".join(deps)
    return f"""    <worksheet name={q(name)}>
      <table>
        <view>
          <datasources>
            <datasource caption={q(DS_CAPTION)} name={q(DS)} />
          </datasources>
          <datasource-dependencies datasource={q(DS)}>
{deps_xml}
          </datasource-dependencies>
{view_extra}          <aggregation value='true' />
        </view>
        <style />
        <panes>
          <pane selection-relaxation-option='selection-relaxation-allow'>
            <view>
              <breakdown value='auto' />
            </view>
            <mark class={q(mark)} />
{encodings}          </pane>
        </panes>
        <rows>{escape(rows)}</rows>
        <cols>{escape(cols)}</cols>
      </table>
    </worksheet>"""


KPI_TILES = ["Incidents", "Median resolution (h)", "SLA met (%)", "First-contact resolution (%)",
             "Reopen rate (%)", "Avg reassignments"]


def worksheets_xml() -> tuple[str, list[str]]:
    sheets, names = [], []

    def add(name, xml):
        names.append(name)
        sheets.append(xml)

    for kpi in KPI_TILES:
        add(kpi, worksheet(kpi, [kpi], mark="Text", text_measure=kpi))
    add("Incidents per week", worksheet("Incidents per week", ["Incidents"], rows="{m0}", cols="{opened_week_start}",
                                        mark="Bar", dims=[("opened_week_start", True)]))
    add("Median resolution per week", worksheet("Median resolution per week", ["Median resolution (h)"],
                                                rows="{m0}", cols="{opened_week_start}", mark="Line",
                                                dims=[("opened_week_start", True)]))
    add("SLA met per week", worksheet("SLA met per week", ["SLA met (%)"], rows="{m0}", cols="{opened_week_start}",
                                      mark="Line", dims=[("opened_week_start", True)]))
    add("SLA met by priority", worksheet("SLA met by priority", ["SLA met (%)"], rows="{m0}", cols="{priority}",
                                         mark="Bar", dims=[("priority", False)]))
    add("Top 10 categories", worksheet("Top 10 categories", ["Incidents"], rows="{category_top10}", cols="{m0}",
                                       mark="Bar", dims=[("category_top10", False)]))
    validation_measures = [c[1] for c in CALCS]
    add("KPI Validation", worksheet("KPI Validation", validation_measures, rows="{opened_week_start}",
                                    cols=f"[{DS}].[:Measure Names]", mark="Text",
                                    dims=[("opened_week_start", False)], measure_names=True))
    return "  <worksheets>\n" + "\n".join(sheets) + "\n  </worksheets>", names


# --------------------------------------------------------------------------
# Dashboard + windows
# --------------------------------------------------------------------------
DASHBOARD = "Service Desk Overview (legacy)"


def dashboard_xml() -> tuple[str, list[str]]:
    zones, used, zid = [], [], 10

    def zone(name, x, y, w, h):
        nonlocal zid
        zid += 1
        used.append(name)
        zones.append(f"          <zone h='{h}' id='{zid}' name={q(name)} w='{w}' x='{x}' y='{y}' />")

    title = ("          <zone h='6000' id='2' type='text' w='100000' x='0' y='0'>\n"
             "            <formatted-text>\n"
             "              <run bold='true' fontsize='16'>Service Desk Overview (legacy Tableau dashboard)</run>\n"
             "              <run>&#10;Real ServiceNow incident log (UCI, CC BY 4.0) - incidents opened 29 Feb - 31 May 2016</run>\n"
             "            </formatted-text>\n"
             "          </zone>")
    w6 = [16667, 16667, 16666, 16667, 16667, 16666]
    x = 0
    for kpi, w in zip(KPI_TILES, w6, strict=True):
        zone(kpi, x, 6000, w, 16000)
        x += w
    zone("Incidents per week", 0, 22000, 33333, 38000)
    zone("Median resolution per week", 33333, 22000, 33334, 38000)
    zone("SLA met per week", 66667, 22000, 33333, 38000)
    zone("SLA met by priority", 0, 60000, 50000, 40000)
    zone("Top 10 categories", 50000, 60000, 50000, 40000)
    xml = f"""  <dashboards>
    <dashboard name={q(DASHBOARD)}>
      <style />
      <size maxheight='1000' maxwidth='1400' minheight='1000' minwidth='1400' />
      <zones>
        <zone h='100000' id='1' type='layout-basic' w='100000' x='0' y='0'>
{title}
{chr(10).join(zones)}
        </zone>
      </zones>
    </dashboard>
  </dashboards>"""
    return xml, used


def windows_xml(sheet_names: list[str], dashboard_sheets: list[str]) -> str:
    win = []
    for name in sheet_names:
        win.append(f"""    <window class='worksheet' name={q(name)}>
      <cards>
        <edge name='left'>
          <strip size='160'>
            <card type='pages' />
            <card type='filters' />
            <card type='marks' />
          </strip>
        </edge>
        <edge name='top'>
          <strip size='2147483647'>
            <card type='columns' />
          </strip>
          <strip size='2147483647'>
            <card type='rows' />
          </strip>
          <strip size='31'>
            <card type='title' />
          </strip>
        </edge>
      </cards>
    </window>""")
    viewpoints = "\n".join(f"        <viewpoint name={q(n)} />" for n in dashboard_sheets)
    win.append(f"""    <window class='dashboard' maximized='true' name={q(DASHBOARD)}>
      <viewpoints>
{viewpoints}
      </viewpoints>
      <active id='-1' />
    </window>""")
    return "  <windows source-height='30'>\n" + "\n".join(win) + "\n  </windows>"


def build_twb(header: list[str]) -> str:
    sheets, names = worksheets_xml()
    dash, used = dashboard_xml()
    return f"""<?xml version='1.0' encoding='utf-8' ?>

<workbook source-build='2018.1.0 (20181.18.0213.2206)' source-platform='win' version='18.1' xmlns:user='http://www.tableausoftware.com/xml/user'>
  <preferences>
    <preference name='ui.encoding.shelf.height' value='24' />
    <preference name='ui.shelf.height' value='26' />
  </preferences>
{datasource_xml(header)}
{sheets}
{dash}
{windows_xml(names, used)}
</workbook>
"""


def main() -> None:
    if not EXTRACT.exists():
        raise SystemExit(f"{EXTRACT} not found - run the pipeline first (it exports the Tableau extract)")
    with open(EXTRACT, newline="", encoding="utf-8") as fh:
        header = next(csv.reader(fh))
    missing = [c for c in header if c not in COLUMN_TYPES]
    if missing:
        raise SystemExit(f"Unknown columns in extract, add them to COLUMN_TYPES: {missing}")
    twb = build_twb(header)
    OUT.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(OUT, "w", compression=zipfile.ZIP_DEFLATED) as z:
        z.writestr(TWB_NAME, twb)
        z.write(EXTRACT, f"{DATA_DIR}/incidents.csv")
    print(f"Wrote {OUT} ({OUT.stat().st_size / 1e6:.1f} MB)")


if __name__ == "__main__":
    main()
