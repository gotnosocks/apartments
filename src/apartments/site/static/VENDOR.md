# Third-party scripts in this folder

Served from the site itself, never a CDN (the site's Content-Security-Policy
allows scripts from 'self' only). Both draw on a canvas and set styles only
through the CSSOM, so `style-src 'self'` needs no exception. Only the
Research pages with zoomable fit charts load them (`fitchart.js`).

| File | Package | Version | Licence | Source |
| --- | --- | --- | --- | --- |
| `chart-4.5.1.min.js` | chart.js | 4.5.1 | MIT | `dist/chart.umd.min.js` from https://registry.npmjs.org/chart.js/-/chart.js-4.5.1.tgz |
| `chartjs-plugin-zoom-2.2.0.min.js` | chartjs-plugin-zoom | 2.2.0 | MIT | `dist/chartjs-plugin-zoom.min.js` from https://registry.npmjs.org/chartjs-plugin-zoom/-/chartjs-plugin-zoom-2.2.0.tgz |

sha256 of the files as committed:

```
48444a82d4edcb5bec0f1965faacdde18d9c17db3063d042abada2f705c9f54a  chart-4.5.1.min.js
e4a088e5bab93be6ee47c939eeb9ebaa80e0b39156d4bdfd1af9c844be81b6c4  chartjs-plugin-zoom-2.2.0.min.js
```

The zoom plugin's pinch and pan need hammer.js, which is left out on
purpose: on a phone a touch on the chart keeps scrolling the page, and the
"Set the range by hand" form zooms instead.

To upgrade, take the same `dist` file from the new package tarball, rename it
with its version, update the script tags in `templates/research_frontier.html`
and this table.

## chart.js licence

The MIT License (MIT)

Copyright (c) 2014-2024 Chart.js Contributors

Permission is hereby granted, free of charge, to any person obtaining a copy of this software and associated documentation files (the "Software"), to deal in the Software without restriction, including without limitation the rights to use, copy, modify, merge, publish, distribute, sublicense, and/or sell copies of the Software, and to permit persons to whom the Software is furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY, FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM, OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE SOFTWARE.

## chartjs-plugin-zoom licence

The MIT License (MIT)

Copyright (c) 2013-2021 chartjs-plugin-zoom contributors

Permission is hereby granted, free of charge, to any person obtaining a copy of this software and associated documentation files (the "Software"), to deal in the Software without restriction, including without limitation the rights to use, copy, modify, merge, publish, distribute, sublicense, and/or sell copies of the Software, and to permit persons to whom the Software is furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY, FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM, OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE SOFTWARE.
