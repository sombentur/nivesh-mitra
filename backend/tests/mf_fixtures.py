"""Small samples in AMFI's real formats (checked against the live files on 30-Sep-2026)."""

NAV_ALL = """Scheme Code;ISIN Div Payout/ ISIN Growth;ISIN Div Reinvestment;Scheme Name;Plan;Option;Net Asset Value;Date

Open Ended Schemes(Equity Schemes - Flexi Cap Fund)

Parag Parikh Mutual Fund

122639;INF879O01027;-;Parag Parikh Flexi Cap Fund;Direct Plan;Growth;{ppfas_d};{d}
122640;INF879O01019;-;Parag Parikh Flexi Cap Fund;Regular Plan;Growth;80.1000;{d}

Open Ended Schemes(Equity Scheme - ELSS)

Axis Mutual Fund

120503;INF846K01EW2;-;Axis ELSS Tax Saver Fund;Direct Plan;Growth Option;98.1200;{d}
120504;INF846K01EX0;INF846K01EY8;Axis ELSS Tax Saver Fund;Direct Plan;IDCW Option;30.0100;{d}

Open Ended Schemes(Other Scheme - Index Funds)

UTI Mutual Fund

120716;INF789F01XA0;-;UTI Nifty 50 Index Fund;;;165.2300;{d}
148001;INF789F1A001;-;UTI CRISIL SDL Maturity June 2027 Index Fund;Direct Plan;Growth;11.2000;{d}

Open Ended Schemes(Debt Scheme - Corporate Bond Fund)

ICICI Prudential Mutual Fund

130947;INF109KA1I84;-;ICICI Prudential Corporate Bond Fund;;;14.9782;24-Apr-2020

Close Ended Schemes(Income/Debt Oriented Schemes - Fixed Term Plan)

SBI Mutual Fund

140001;INF200KA1FTP;-;SBI FMP Series 99;Direct Plan;Growth;12.0000;{d}
"""

MASTER = """AMC,Code,Scheme Name,Scheme Type,Scheme Category,Scheme NAV Name,Scheme Minimum Amount,Launch Date, Closure Date,ISIN Div Payout/ ISIN GrowthISIN Div Reinvestment
PPFAS Asset Management Pvt. Ltd,122639,Parag Parikh Flexi Cap Fund,Open Ended,Equity Scheme - Flexi Cap Fund,Parag Parikh Flexi Cap Fund - Direct Plan - Growth,1000,24-May-2013,24-May-2013,INF879O01027
PPFAS Asset Management Pvt. Ltd,122640,Parag Parikh Flexi Cap Fund,Open Ended,Equity Scheme - Flexi Cap Fund,Parag Parikh Flexi Cap Fund - Regular Plan - Growth,1000,24-May-2013,24-May-2013,INF879O01019
Axis Asset Management Co. Ltd.,120503,Axis ELSS Tax Saver Fund,Open Ended,Equity Scheme - ELSS,Axis ELSS Tax Saver Fund - Direct Growth,500,01-Jan-2013,01-Jan-2013,INF846K01EW2
Axis Asset Management Co. Ltd.,120504,Axis ELSS Tax Saver Fund,Open Ended,Equity Scheme - ELSS,Axis ELSS Tax Saver Fund - Direct IDCW,500,01-Jan-2013,01-Jan-2013,INF846K01EX0INF846K01EY8
UTI Asset Management Co Ltd,120716,UTI Nifty 50 Index Fund,Open Ended,Other Scheme - Index Funds,UTI Nifty 50 Index Fund - Direct Plan - Growth Option,5000,01-Jan-2013,01-Jan-2013,INF789F01XA0
"""

NAV_HISTORY = """Scheme Code;NAV Name;Plan;Option;ISIN Div Payout/ISIN Growth;ISIN Div Reinvestment;Net Asset Value;Date

Open Ended Schemes ( Equity Schemes - Flexi Cap Fund )


Parag Parikh Mutual Fund
{rows}
"""


def nav_all(d: str = "29-Sep-2026", ppfas_d: str = "90.5000") -> str:
    return NAV_ALL.format(d=d, ppfas_d=ppfas_d)


def nav_history(entries: list[tuple[int, str, float]]) -> str:
    rows = "\n".join(f"{code};Fund - Direct Plan - Growth;Direct Plan;Growth;;;{nav};{d}" for code, d, nav in entries)
    return NAV_HISTORY.format(rows=rows)
