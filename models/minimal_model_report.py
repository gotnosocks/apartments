"""Render a self-contained, interactive report for the local minimal model."""
from pathlib import Path
import argparse
import html
import json

import numpy as np
import pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots

BLUE='#24455e';TEAL='#238b82';ORANGE='#c27b36';MUTED='#73818c'


def layout(fig, height=380):
    fig.update_layout(template='plotly_white',height=height,font={'family':'Arial, sans-serif','size':13,'color':BLUE},
                      margin={'l':55,'r':25,'t':35,'b':48},paper_bgcolor='white',plot_bgcolor='white',
                      legend={'orientation':'h','y':1.13,'x':0},hovermode='x unified')
    fig.update_xaxes(showgrid=False,zeroline=False)
    fig.update_yaxes(gridcolor='#e7ecef',zeroline=False)
    return fig


def table(headers,rows):
    return '<table><thead><tr>'+''.join('<th>'+html.escape(str(x))+'</th>' for x in headers)+'</tr></thead><tbody>'+''.join('<tr>'+''.join('<td>'+html.escape(str(x))+'</td>' for x in row)+'</tr>' for row in rows)+'</tbody></table>'


def report(root,output):
    root=Path(root);output=Path(output);output.mkdir(parents=True,exist_ok=True)
    results=json.loads((root/'results.json').read_text());c=results['coverage']
    temporal=results['temporal_validation']['scores'];cold=results['unseen_unit_validation']['scores'];main=temporal['model']
    index=pd.read_parquet(root/'rent_index.parquet');validation=pd.read_parquet(root/'temporal_validation.parquet')
    data=pd.read_parquet(root/'model_data.parquet');diagnostics=pd.read_parquet(root/'fit_diagnostics.parquet')
    encoder=json.loads((root/'encoder.json').read_text())
    with np.load(root/'model.npz',allow_pickle=False) as model:
        a,b=encoder['offsets']['season'];season=model['beta'][a:b]
    season_pct=100*np.expm1(season-season.mean())
    indexed=index.set_index('period')
    yoy=100*(indexed.loc['2026-08-01','smooth_index']/indexed.loc['2025-08-01','smooth_index']-1)
    pre=index[index.period.eq('2020-02-01')].smooth_index.iloc[0]
    trough=index[index.period.between('2020-03-01','2021-12-01')].sort_values('smooth_index').iloc[0]
    decline=100*(trough.smooth_index/pre-1)
    season_peak=int(np.argmax(season_pct));season_low=int(np.argmin(season_pct))
    month_names=['Jan','Feb','Mar','Apr','May','Jun','Jul','Aug','Sep','Oct','Nov','Dec']
    fig=make_subplots(rows=2,cols=1,shared_xaxes=True,vertical_spacing=.10,row_heights=[.78,.22])
    fig.add_trace(go.Scatter(x=index.period,y=index.smooth_index,name='Adjusted trend, excluding seasonality',line={'color':TEAL,'width':3}),row=1,col=1)
    fig.add_trace(go.Scatter(x=index.period,y=index.index_with_seasonality,name='Adjusted trend + seasonality',line={'color':BLUE,'width':1},opacity=.5),row=1,col=1)
    fig.add_trace(go.Bar(x=index.period,y=index.observations,name='Unit-month observations',marker_color='#cfdbdf',showlegend=False),row=2,col=1)
    layout(fig,470);fig.update_yaxes(title_text='Index · Jan 2022 = 100',row=1,col=1);fig.update_yaxes(title_text='Count',row=2,col=1)
    trend_chart=fig.to_html(full_html=False,include_plotlyjs=True,config={'displaylogo':False,'responsive':True})
    fig=go.Figure()
    for name,color,mask in [('Previously seen unit',TEAL,validation.seen_unit),('New unit',ORANGE,~validation.seen_unit)]:
        part=validation[mask]
        fig.add_trace(go.Scatter(x=part.asking_rent,y=part.predicted_rent,mode='markers',name=name,
                                marker={'size':5,'color':color,'opacity':.40},hovertemplate='Asked $%{x:,.0f}<br>Predicted $%{y:,.0f}<extra>'+name+'</extra>'))
    lo,hi=700,52000
    fig.add_trace(go.Scatter(x=[lo,hi],y=[lo,hi],mode='lines',line={'color':MUTED,'dash':'dash'},name='Perfect prediction'))
    layout(fig,430);fig.update_layout(hovermode='closest');fig.update_xaxes(type='log',title='Actual initial asking rent ($/month)');fig.update_yaxes(type='log',title='Held-out prediction ($/month)')
    prediction_chart=fig.to_html(full_html=False,include_plotlyjs=False,config={'displaylogo':False,'responsive':True})
    fig=go.Figure(go.Bar(x=month_names,y=season_pct,marker_color=[TEAL if x>=0 else MUTED for x in season_pct]))
    layout(fig,300);fig.update_layout(showlegend=False);fig.update_yaxes(title='Difference from annual center (%)')
    season_chart=fig.to_html(full_html=False,include_plotlyjs=False,config={'displaylogo':False,'responsive':True})
    metrics_rows=[]
    for label,value in [('Model · all 2026 test listings',main),('Bedroom-only recent-rent baseline',temporal['bedroom_baseline']),
                         ('Model without unit effects',results['temporal_validation']['without_unit_effect']),
                         ('Model · previously seen units',temporal['seen_unit_model']),
                         ('Last observed rent · same seen units',temporal['last_unit_rent_baseline']),
                         ('Model · units new in 2026',temporal['unseen_unit_model'])]:
        metrics_rows.append([label,f"{value['observations']:,}",f"{value['median_absolute_percent_error']:.1f}%",f"{value['within_20_percent']:.1f}%"])
    error_by=[]
    validation['absolute_percent_error']=100*np.abs(validation.predicted_rent/validation.asking_rent-1)
    for beds,group in validation.groupby('bedrooms'):
        error_by.append(['Studio' if beds==0 else f"{int(beds)} bedroom{'s' if beds!=1 else ''}",f'{len(group):,}',f'{group.absolute_percent_error.median():.1f}%'])
    labels={'no_dated_own_active_event':'No dated initial active event belonging to this listing',
            'outside_date_window':'Before 2010 or in partial September 2026',
            'conflicting_initial_prices':'Different prices for the same initial date',
            'invalid_or_extreme_initial_ask':'Initial asking rent outside $750–$50,000',
            'invalid_or_missing_layout':'Missing/invalid layout, >5 bedrooms or >5 bathrooms',
            'furnished':'Explicit furnished evidence', 'short_term':'Explicit lease shorter than six months',
            'explicit_concession':'Explicit free-month or net-effective-rent fields',
            'conflicting_layout_same_unit_month':'Conflicting layouts within one unit-month'}
    exclusion_rows=[[labels.get(r['reason'],r['reason']),f"{r['listing_ids']:,}"] for r in c['exclusions'] if r['listing_ids']]
    years=data.groupby(data.period.dt.year).agg(observations=('unit_id','size'),units=('unit_id','nunique'))
    years.to_parquet(output/'coverage_by_year.parquet')
    summary={'year_over_year_august_2026_percent':float(yoy),'covid_era_trough_month':str(trough.period.date()),
             'trough_vs_february_2020_percent':float(decline),'seasonal_peak':month_names[season_peak],
             'seasonal_low':month_names[season_low], 'temporal_validation_by_bedrooms':error_by,
             'note':'Descriptive model estimates on selected asking listings, not signed rents or a complete market census'}
    (output/'report_summary.json').write_text(json.dumps(summary,indent=2))
    incremental=encoder.get('bedroom_encoding')=='incremental'
    bedroom_description=('Bedrooms use cumulative indicators: >0, >1, >2, >3, and >4. A two-bedroom listing activates the first two terms; each coefficient is an additional-bedroom contribution on the log-rent scale. Regularization shrinks those increments separately. Studios activate none of them.' if incremental else 'Bedrooms use exact-category indicators for 1–5 bedrooms, with studios as the reference.')
    body=f'''<header><div class="eyebrow">Chelsea rental archive · Local model pass · September 17, 2026</div>
<h1>A simple model of asking rents</h1>
<p class="lede">A broad first pass using canonical unit identities, clean listing-level prices, and a small set of predictors. Fits and validation ran locally on the Thelio.</p></header>
<div class="cards"><div><strong>{c['included_listing_ids']:,}</strong><span>rental listings retained · {c['retained_percent']:.1f}% of input</span></div><div><strong>{c['units']:,}</strong><span>canonical units · {c['buildings']:,} buildings</span></div><div><strong>{main['median_absolute_percent_error']:.1f}%</strong><span>median error on withheld 2026 prices</span></div></div>
<section><h2>What stands out</h2><p>The model retained most of the data and gives a useful first estimate: <b>{main['within_20_percent']:.1f}% of 2026 test observations land within 20% of their asking price</b>. A bedroom-only baseline has {temporal['bedroom_baseline']['median_absolute_percent_error']:.1f}% median error. Knowing the exact unit helps, but the building, layout and time effects also work for new units.</p>
<p>The fitted, seasonally adjusted trend is <b>{yoy:+.1f}% from August 2025 to August 2026</b>. The 2020–21 trough occurs in {trough.period.strftime('%B %Y')}, at {decline:.1f}% relative to February 2020. These describe the selected listing sample; they are not a census of rents or a causal market estimate.</p>
<p class="callout">The main weakness: the 2026 test predictions are about {abs(main['median_signed_percent_error']):.1f}% too low at the median. The forecast deliberately holds the last trained market level flat, so it misses further rent growth. The full-data fit shown below includes 2026.</p></section>
<section><h2>Adjusted rent history</h2><p>A smooth monthly trend controls for layout, reported size, building and repeated unit identity. The faint line adds seasonality; the bars show how much data supports each month.</p>{trend_chart}<p class="caption">Full fit: January 2010–August 2026. Index base is January 2022. Curves are point estimates; no uncertainty bands were estimated.</p></section>
<section><h2>Does it predict prices it did not see?</h2><p>Settings were chosen using 2025 only. The temporal test trained through December 2025 and withheld all January–August 2026 asking prices. Median absolute percentage error is the typical proportional prediction error; lower is better.</p>
{table(['Temporal test','Observations','Median absolute error','Within 20%'],metrics_rows)}
{prediction_chart}<p class="caption">Both axes use a logarithmic scale. Points are genuinely withheld asking-price targets, not in-sample fitted values.</p>
<p>A separate test withholds roughly 20% of <em>entire units</em> across all dates. It uses fixed settings selected independently of those units. Median error is <b>{cold['model']['median_absolute_percent_error']:.1f}%</b> on {cold['model']['observations']:,} observations, versus {cold['bedroom_baseline']['median_absolute_percent_error']:.1f}% for a same-month, same-bedroom baseline. This measures estimating an unseen unit when other units reveal that period’s market conditions; it is not a future-market forecast.</p>
<p class="caption">Both tests are retrospective. Attributes and cleaning flags come from later archived captures of the same advertisement. This is not a fully as-of-date backtest. Almost all tested buildings already have training data; performance on new buildings is not established.</p>
<details><summary>2026 errors by apartment size</summary>{table(['Layout','Test observations','Median absolute error'],error_by)}</details></section>
<section><h2>Seasonality</h2><p>The fitted seasonal pattern is highest in {month_names[season_peak]} and lowest in {month_names[season_low]}, after accounting for the smooth trend and observed mix of units.</p>{season_chart}<p class="caption">A shared month-of-year pattern over the full sample. It need not hold identically in every year or building.</p></section>
<section><h2>What was kept, and what was left out</h2><p>Each listing contributes its earliest dated <code>ACTIVE</code> asking-price event from captures of that same listing ID. Repeated captures count once. Multiple listings of one canonical unit in one month become one median observation, yielding <b>{c['model_observations']:,} unit-month observations</b>. Historical events mentioned only by other listings do not borrow those listings’ attributes.</p>
<p><b>Missing square footage remains usable:</b> {c['missing_sqft_observations']:,} observations ({100*c['missing_sqft_observations']/c['model_observations']:.1f}%) have no reported usable area. Their size term is centered at the training-set bedroom-group median with a missingness indicator. Four implausible size values were treated as missing. Bedrooms must be 0–5 and bathrooms 1–5 in half-bath increments.</p>
{table(['Exclusion, applied in this order','Listing IDs'],exclusion_rows)}
<p class="caption">Counts are mutually exclusive and sum to {c['source_listing_ids']-c['included_listing_ids']:,}. Furnished listings and concession offers are a scope choice for this simple pass, not inherently bad data. All original records remain in the transform.</p></section>
<section><h2>The model in plain terms</h2><p>Log asking rent = layout + optional size + building effect + unit effect + smooth monthly trend + seasonality. Building and unit effects are pulled toward the overall pattern when evidence is thin. A robust loss reduces the influence of unusual prices rather than allowing a few extremes to drive the fit.</p>
<p>{bedroom_description}</p>
<p>This is a penalized point estimate, not a Bayesian posterior. Six small settings combinations were compared on 2025. The final local pipeline took {results['runtime_seconds']:.0f} seconds, including preparation, tuning, validation and the full fit. All linear solves converged; the last robust-fit objective change was {results['fit']['robust_objective_relative_change']:.2g} relative.</p>
<p>There are no floor guesses, photo features, inferred renovation dates, amenity effects, or manual-review annotations in this pass. Layout changes can enter through each listing’s own attributes, but the model treats the remaining unit effect as stable over time.</p></section>
<section><h2>How to use this first pass</h2><p>Use it to explore the adjusted asking-rent trend and compare a listing with similar units in the same building and period. Expect weaker estimates for unusual luxury layouts, unseen buildings, or properties whose condition changed. These are nominal initial asking rents, not achieved rents, signed leases, or inflation-adjusted returns.</p>
<p>Keep this as a reproducible baseline. The next useful refinement would be better treatment of concessions and condition changes, followed by a true as-of-date evaluation if future pricing is the goal.</p></section>
<footer>Dataset: <code>{html.escape(Path(c['dataset']).name)}</code><br>Model artifacts: <code>{html.escape(str(root))}</code><br>Saved inputs, selection audit, coefficients, weights, held-out predictions and source hashes accompany this report.</footer>'''
    styles='''*{box-sizing:border-box}body{margin:0;background:#f4f5f2;color:#253c4a;font:16px/1.65 Arial,sans-serif}main{max-width:1120px;margin:0 auto;padding:55px 38px}header{max-width:860px;margin-bottom:32px}.eyebrow{text-transform:uppercase;letter-spacing:.12em;color:#61717b;font-size:11px;font-weight:700}h1{font:46px/1.1 Georgia,serif;letter-spacing:-1px;margin:18px 0}h2{font:28px/1.25 Georgia,serif;margin:0 0 18px}.lede{font-size:19px;color:#5a6a74}.cards{display:grid;grid-template-columns:repeat(3,1fr);gap:14px;margin:30px 0}.cards>div{background:#fff;padding:22px;border-top:3px solid #238b82}.cards strong{display:block;font-size:34px;font-weight:500}.cards span{display:block;color:#61717b;font-size:13px}section{background:#fff;padding:30px;margin:20px 0;border:1px solid #e4e9e8}p{margin:12px 0}.callout{padding:16px 20px;background:#f7f1e7;border-left:3px solid #c27b36}table{border-collapse:collapse;width:100%;font-size:13px;margin:22px 0}th{text-align:left;background:#edf2f3;color:#465d6a}th,td{padding:11px 12px;border-bottom:1px solid #e3e9eb}td:not(:first-child),th:not(:first-child){text-align:right;font-variant-numeric:tabular-nums}.caption,footer{font-size:12px;color:#6a7982}summary{cursor:pointer;font-weight:600}code{font-size:.87em;overflow-wrap:anywhere}footer{padding:12px 5px 35px}@media(max-width:700px){main{padding:25px 12px}h1{font-size:34px}section{padding:20px 14px}.cards{grid-template-columns:1fr}.cards>div{padding:14px}table{font-size:11px}th,td{padding:8px 5px}}'''
    (output/'report.html').write_text('<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>Chelsea · Minimal asking-rent model</title><style>'+styles+'</style></head><body><main>'+body+'</main></body></html>')
    markdown=f'''# Minimal canonical-unit asking-rent model — September 17, 2026

Fit locally on the Thelio using `{Path(c['dataset']).name}`.

- Retained **{c['included_listing_ids']:,} / {c['source_listing_ids']:,} listing IDs ({c['retained_percent']:.1f}%)**.
- Modeled **{c['model_observations']:,} unit-month observations**, **{c['units']:,} units**, **{c['buildings']:,} buildings**.
- Window: January 2010–August 2026. {100*c['missing_sqft_observations']/c['model_observations']:.1f}% of observations have missing size and remain in the model.
- Withheld 2026 median absolute error: **{main['median_absolute_percent_error']:.1f}%**, versus **{temporal['bedroom_baseline']['median_absolute_percent_error']:.1f}%** for the bedroom-only baseline. **{main['within_20_percent']:.1f}%** are within 20%.
- Entirely withheld units: **{cold['model']['median_absolute_percent_error']:.1f}%** median error. This tests unseen-unit estimation in observed market periods.
- Adjusted trend: **{yoy:+.1f}%** August 2026 vs August 2025. 2020–21 trough: **{decline:.1f}%** vs February 2020 in {trough.period.strftime('%B %Y')}.
- Full local fitting pipeline: **{results['runtime_seconds']:.0f} seconds**.

See [the interactive report](report.html) for charts, exclusions and validation details.

## Method

Robust penalized regression on log initial asking rent, with {'incremental bedroom thresholds (>0, >1, >2, >3, >4)' if incremental else 'bedroom categories'},
bathrooms, optional size, building and unit effects, a smooth monthly trend and
month-of-year seasonality. Six settings combinations were selected using 2025;
2026 prices stayed withheld until final evaluation. A separate 20% unit holdout
uses independent fixed settings and training-only scales.

Each advertisement uses its own first active event and its own attributes.
Repeated source captures count once; duplicate listings within a unit-month become
one median observation. Source data and review decisions are not changed.

## Limits

These are nominal asking prices, not signed rents. Explicit concessions, furnished
and very short-term offers are excluded. Conditions and renovation dates remain
unmodeled beyond reported layout changes. No posterior or uncertainty intervals
were estimated. The temporal test is retrospective with later archived covariates,
not a live as-of-date backtest; it underpredicts 2026 by {abs(main['median_signed_percent_error']):.1f}% at the median.
New-building performance is not established.

## Reproduce and reuse

```sh
OPENBLAS_NUM_THREADS=2 OMP_NUM_THREADS=2 uv run --locked --extra model python models/minimal_rent_model.py \\
  --dataset {c['dataset']} \\
  --output /path/to/new-model-run
uv run --locked --extra model python models/minimal_model_report.py --model /path/to/new-model-run --output /path/to/report
```

Import `load_model(directory)` and `predict(model, dataframe)` from
`models/minimal_rent_model.py` to reuse the saved point estimate. Inputs need
`unit_id`, `building` (canonical building slug), `period` (month-start timestamp),
`bedrooms`, `bathrooms`, and `square_feet` (NaN allowed). `predict` returns log rent;
exponentiate for the predicted median asking rent. Unknown units/buildings receive
zero group offsets; future months hold the final smooth trend flat plus seasonality.

Artifacts are in `{root}`. Selection audit retains an exclusion reason for every
dropped listing. The final report and parquet tables preserve reproducibility.
'''
    (output/'report.md').write_text(markdown)
    print(json.dumps({'report':str(output/'report.html'),'summary':summary},indent=2))


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--model',type=Path,required=True);parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args();report(args.model,args.output)
