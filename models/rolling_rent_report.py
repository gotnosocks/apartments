"""Render a completed sequential experiment as a standalone interactive report."""
from __future__ import annotations

import argparse
import hashlib
import html
import json
from pathlib import Path

import plotly
import plotly.graph_objects as go
from plotly.subplots import make_subplots

from apartments.corrections import canonical
from apartments.research_pipeline import _verified_bundle, digest, publish_bundle

LABELS = {'annual_frozen':'Annual frozen', 'monthly':'Monthly refit',
          'monthly_recent':'Monthly + recent adjustment'}
COLORS = {'annual_frozen':'#b45309', 'monthly':'#2563eb', 'monthly_recent':'#059669'}


def render(experiment, output):
    root = Path(experiment)
    pm, pf = _verified_bundle(root/'protocol',retain={'protocol.json'})
    sm, sf = _verified_bundle(root/'summary',retain={'report.json'})
    protocol = json.loads(pf['protocol.json']); report = json.loads(sf['report.json'])
    ph = hashlib.sha256(canonical(protocol).encode()).hexdigest()
    if pm.get('protocol_sha256') != ph or sm.get('protocol_sha256') != ph:
        raise ValueError('Report and protocol do not match')
    if report.get('version') != 'chelsea-sequential-monthly-v1':
        raise ValueError('Unsupported completed experiment')
    months = report['monthly_reports']
    if ([r['month'] for r in months] != [s['month'][:7] for s in protocol['splits']]
            or report['months'] != len(months)):
        raise ValueError('Report does not cover all declared months')
    # Verify the chain that the report claims, including all monthly prediction files.
    chain = []
    for month in months:
        manifest, files = _verified_bundle(root/month['month']/'forecast',retain={'report.json'})
        if manifest.get('protocol_sha256') != ph or json.loads(files['report.json']) != month:
            raise ValueError('Monthly report provenance mismatch')
        chain.append(hashlib.sha256(canonical(manifest).encode()).hexdigest())
    if hashlib.sha256(canonical(chain).encode()).hexdigest() != sm.get('forecast_chain_sha256'):
        raise ValueError('Forecast chain mismatch')
    figure = make_subplots(rows=3,cols=1,shared_xaxes=True,vertical_spacing=.08,
                           subplot_titles=('Point prediction error','Nominal 95% band: observed coverage',
                                           'Nominal 95% band: median width relative to prediction'))
    dates = [row['month']+'-01' for row in months]
    for policy,label in LABELS.items():
        values = [row['metrics']['policies'][policy] for row in months]
        series = [([v['median_absolute_percent_error'] for v in values],'Median error (%)'),
                  ([v['intervals']['95'].get('coverage_percent') for v in values],'Coverage (%)'),
                  ([v['intervals']['95'].get('median_width_percent_of_prediction') for v in values],'Width (%)')]
        for row,(y,title) in enumerate(series,1):
            figure.add_trace(go.Scatter(x=dates,y=y,name=label,legendgroup=policy,showlegend=row==1,
                line={'color':COLORS[policy]},mode='lines+markers',marker={'size':4},
                hovertemplate='%{x|%b %Y}<br>'+title+': %{y:.2f}<extra>'+label+'</extra>'),row=row,col=1)
    figure.add_hline(y=95,line_dash='dash',line_color='#64748b',row=2,col=1)
    figure.update_yaxes(title_text='Percent',row=1,col=1)
    figure.update_yaxes(title_text='Percent',range=[0,100],row=2,col=1)
    figure.update_yaxes(title_text='Percent',row=3,col=1)
    figure.update_layout(height=940,template='plotly_white',margin={'l':70,'r':35,'t':75,'b':45},
                          legend={'orientation':'h','y':1.08},hovermode='x unified')
    graph = figure.to_html(full_html=False,include_plotlyjs=True,div_id='monthly-validation',
                           config={'responsive':True,'displaylogo':False})
    header = ['Slice','Policy','Rows','Median error','Signed bias','95% coverage','Band rows','Pooled-band rows','Median band width']
    rows = []
    for name,group in [('All months',report['pooled']),*report['years'].items(),*report['strata'].items()]:
        for policy,label in LABELS.items():
            m = group['policies'][policy]; interval=m['intervals']['95']
            fmt = lambda value: 'Unavailable' if value is None else f'{value:.2f}%'
            display_name = {'seen_unit':'Seen units','new_unit_seen_building':'New units, seen buildings',
                            'new_building':'New buildings'}.get(name,name)
            rows.append([display_name,label,str(group['rows']),fmt(m['median_absolute_percent_error']),
                         fmt(m['median_signed_percent_error']),fmt(interval.get('coverage_percent')),
                         str(interval['available_rows']),str(interval.get('pooled_fallback_rows',0)),
                         fmt(interval.get('median_width_percent_of_prediction'))])
    table = '<table><thead><tr>'+''.join('<th>'+html.escape(x)+'</th>' for x in header)+'</tr></thead><tbody>'
    table += ''.join('<tr>'+''.join('<td>'+html.escape(x)+'</td>' for x in row)+'</tr>' for row in rows)+'</tbody></table>'
    limits = ''.join('<li>'+html.escape(x)+'</li>' for x in report['limitations'])
    body = f'''<!doctype html><html lang="en"><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1"><title>Chelsea monthly pricing validation</title>
<style>body{{font:16px/1.5 system-ui,sans-serif;max-width:1200px;margin:32px auto;padding:0 20px;color:#172033}}
h1{{font-size:28px}}p{{max-width:950px}}table{{border-collapse:collapse;width:100%;font-size:13px}}
th,td{{text-align:left;padding:9px;border-bottom:1px solid #dbe2eb}}th{{background:#eef3f8}}
.scroll{{overflow-x:auto}}.note{{padding:16px;background:#f1f5f9}}code{{overflow-wrap:anywhere}}</style>
<h1>Chelsea monthly pricing validation</h1>
<p>{report['months']} monthly origins, {report['pooled']['rows']:,} historical unit-month predictions.
Compare updating every month, holding a model fixed for a year, and adjusting a monthly model using earlier errors.</p>
<p class="note">These are retrospective asking-rent predictions using later-collected attributes.
The 95% label describes the intended interval level; measured coverage can be lower.
Initial months have no band, and sparse familiarity groups can use pooled earlier errors.
Hover for values and click legend entries to compare policies.</p>
{graph}<h2>Year and familiarity comparisons</h2>
<p>Point errors use every row. Coverage and width use only rows with an available band.
Width is the full interval width as a percentage of predicted rent. Familiarity is measured against
the current monthly training set for all three policies. Intervals are empirical prediction bands,
not coefficient confidence intervals.</p><div class="scroll">{table}</div>
<h2>Interpretation limits</h2><ul>{limits}</ul>
<p>Verified protocol: <code>{ph}</code>. Full denominators, fallback counts, tail misses, interval scores,
and month-specific calibration rules are in the accompanying JSON report.</p></html>'''
    return publish_bundle(output,{'report.html':body,'report.json':sf['report.json'].decode(),
                                  'figure.json':figure.to_json(),'driver.py':Path(__file__).read_text()},
                          {'version':'monthly-validation-report-v1','protocol_sha256':ph,
                           'summary_manifest_sha256':digest(root/'summary'/'complete.json'),
                           'implementation_sha256':digest(__file__),'plotly_version':plotly.__version__})


if __name__ == '__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--experiment',type=Path,required=True)
    parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args()
    print(canonical(render(args.experiment,args.output)))
