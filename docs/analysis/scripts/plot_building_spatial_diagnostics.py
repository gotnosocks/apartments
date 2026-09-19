"""Plot verified primary and coordinate-sensitivity spatial diagnostics."""
import argparse
import io
import json
from pathlib import Path

import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib.ticker import FormatStrFormatter, MaxNLocator
import numpy as np

from apartments.corrections import canonical
from apartments.research_pipeline import digest, publish_bundle
from models.cohort_spatial_features import records, verified_manifest


def run(primary, sensitivity, output, preview=None):
    primary, sensitivity = Path(primary), Path(sensitivity)
    manifests = [verified_manifest(p) for p in (primary, sensitivity)]
    if any(manifests[0][key] != manifests[1][key] for key in
           ('posterior_sha256', 'source_manifest_sha256', 'spatial_manifest_sha256', 'selection_sha256')):
        raise ValueError('Plots require the same posterior and location evidence')
    results = [json.loads((p/'summary.json').read_text()) for p in (primary, sensitivity)]
    if [r['exclude_coincident_locations'] for r in results] != [False, True]:
        raise ValueError('Expected primary and coincident-coordinate sensitivity artifacts')
    buildings = list(records(primary/'buildings.jsonl'))
    coordinates = np.array([[b['longitude'], b['latitude']] for b in buildings])
    offsets = np.array([b['centered_log_effect']['median'] for b in buildings])
    plt.rcParams.update({'svg.hashsalt': 'chelsea-spatial-diagnostic', 'font.size': 10})
    fig, axes = plt.subplots(1, 2, figsize=(12, 6), gridspec_kw={'width_ratios': [1.2, 1]}, layout='constrained')
    bound = float(max(abs(offsets)))
    points = axes[0].scatter(*coordinates.T, c=offsets, cmap='RdBu_r', vmin=-bound, vmax=bound,
                             s=15, linewidths=.15, edgecolors='white', alpha=.9)
    axes[0].set_aspect(1/np.cos(np.deg2rad(coordinates[:, 1].mean())))
    axes[0].set(xlabel='Longitude', ylabel='Latitude', title='Building-effect posterior medians')
    axes[0].ticklabel_format(useOffset=False)
    axes[0].xaxis.set_major_locator(MaxNLocator(4))
    axes[0].xaxis.set_major_formatter(FormatStrFormatter('%.3f'))
    colorbar = fig.colorbar(points, ax=axes[0], shrink=.7, pad=.03)
    colorbar.set_label('Centered building log-rent offset')
    ylabels = []
    for j, (result, color) in enumerate(zip(results, ['#176b91', '#aa5329'])):
        for i, row in enumerate(result['graphs']):
            y = 3-2*j-i
            value = row['moran_i']
            mid, lower, upper = (value[k] for k in ('median', 'lower_95', 'upper_95'))
            axes[1].errorbar(mid, y, xerr=np.array([[mid-lower], [upper-mid]]),
                             fmt='o', color=color, capsize=4, linewidth=2)
            ylabels.append((y, f"{row['k']} neighbors · {row['buildings']:,} buildings"))
    axes[1].axvline(0, color='#777777', linestyle='--', linewidth=1)
    axes[1].set_yticks([v[0] for v in ylabels], [v[1] for v in ylabels])
    axes[1].set(xlabel="Moran's I (median and 95% posterior interval)", ylim=(-.6, 3.6),
                title='All locations and sensitivity excluding\n'
                      f"{len(results[1]['coincident_buildings_excluded'])} buildings with coincident coordinates")
    axes[1].grid(axis='x', alpha=.2)
    axes[1].text(.03, .08, 'Blue: all verified locations\nBrown: distinct-location sensitivity',
                 transform=axes[1].transAxes, fontsize=9)
    fig.suptitle('Chelsea: spatial structure in unexplained building price effects\n'
                 '24,000 joint draws · selected pre-quarantine fit · conditional associations', fontsize=13)
    buffer = io.StringIO()
    fig.savefig(buffer, format='svg', metadata={'Date': None})
    files = {'spatial-diagnostics.svg': buffer.getvalue(), Path(__file__).name: Path(__file__).read_text(),
             'plot-inputs.json': canonical({'primary': str(primary), 'sensitivity': str(sensitivity)})+'\n'}
    publish_bundle(output, files, {'version': 'building-spatial-diagnostic-figure-v1',
        'primary_manifest_sha256': digest(primary/'complete.json'),
        'sensitivity_manifest_sha256': digest(sensitivity/'complete.json')})
    if preview: fig.savefig(preview, dpi=160)
    plt.close(fig)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ('primary', 'sensitivity', 'output'): parser.add_argument('--'+name, type=Path, required=True)
    parser.add_argument('--preview', type=Path)
    run(**vars(parser.parse_args()))
