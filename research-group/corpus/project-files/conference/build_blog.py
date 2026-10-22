from common import HERE, data_js, page

BODY = """
<main>
<header class="top">
  <div class="kicker">Blog · Apartments project</div>
  <h1>What the 20th floor, a dishwasher and a park view add to a New York rent</h1>
  <p class="byline">22 October 2026 · About a seven-minute read</p>
</header>

<section class="col">
<p class="lede">Every New York renter has asked some version of this: is a higher floor worth $200 more a month? Is
in-unit laundry? We built a model from 1.9 million rental ads to answer that question for each feature, one at a
time, along with how sure we are.</p>

<p>The trick is comparing like with like. Apartments with washers tend to be in newer buildings in pricier
neighbourhoods, so if you just compare rents, you credit the washer with what is really the building and the block.
Our model gives every one of 67,977 buildings its own price level and gives the map its own smooth surface of rent.
A feature that changes inside a building, like the floor, is then priced by comparing units in the same building.</p>

<p>Throughout, we'll translate percentages into dollars on an example $4,000 a month apartment. All figures are
asking rents on StreetEasy in Manhattan and Brooklyn, net of advertised free months.</p>

<h2>Height pays, but only with an elevator</h2>
<p>In an elevator building, each floor up adds a little, and the steps grow as you climb. Against floor 1 of the
same building, the 10th floor asks about 3.8% more (about $150 on our example), the 20th about 6.7% (about $270) and
the 40th about 13.8% ($550). A penthouse adds another 8.3% on top of whatever floor it is on.</p>
</section>
<figure>
  <div class="frame">
    <div class="legend"><span><i class="sw a"></i>Elevator buildings (shaded: 90% range)</span><span><i class="sw b"></i>Walk-ups</span></div>
    <div id="floor"></div>
  </div>
  <figcaption><b>Rent premium over the first floor of the same building.</b> The floor axis is stretched at the bottom, because going from floor 1 to 2 changes more than going from 31 to 32.</figcaption>
</figure>
<section class="col">
<p>Walk-ups go the other way. Each flight of stairs takes about 0.2% off, so a fifth-floor walk-up asks about 0.9%
less than the ground floor. That's around $35 a month for five flights.</p>
<p>This was the biggest single improvement to the model since we added apartment size. When we hid the latest ad of about
190,000 apartments that had been listed before and asked the model to price them, it predicted them clearly better. Penthouses had been underpriced
by about 10%; now the model is off by less than half a percent.</p>

<h2>What features are worth</h2>
<p>For features that vary within a building, the numbers are tight. We give a range because two reasonable versions
of the model disagree slightly, and the truth is most likely in between.</p>
<div class="tw"><table>
<thead><tr><th>Feature</th><th class="n">Premium</th><th class="n">On $4,000</th></tr></thead>
<tbody>
<tr><td>Washer and dryer in the unit (vs. laundry not mentioned)</td><td class="n">+5.7 to +6.3%</td><td class="n">$230 to $250</td></tr>
<tr><td>Laundry room in the building</td><td class="n">+1.4 to +1.7%</td><td class="n">$55 to $70</td></tr>
<tr><td>Dishwasher</td><td class="n">+1.8 to +2.0%</td><td class="n">$75 to $80</td></tr>
<tr><td>Private garden or outdoor space</td><td class="n">+2.3 to +2.9%</td><td class="n">$90 to $115</td></tr>
<tr><td>10% more space than usual for the bedroom count</td><td class="n">+2.3 to +2.4%</td><td class="n">about $95</td></tr>
<tr><td>Ad doesn't say how big the unit is</td><td class="n">−3.8 to −4.0%</td><td class="n">about −$155</td></tr>
</tbody>
<caption>Ranges span our main model and a version that compares buildings with the same mix of units.</caption>
</table></div>
<p>That last line is our favourite. Ads that leave out the square footage ask about 4% less than ads for otherwise
similar apartments. Small units are probably the ones that don't mention it.</p>

<h2>Building features are harder to pin down</h2>
<p>A full-time doorman goes with about 11 to 15% more rent than a comparable building nearby without one. A condo
building runs 6 to 11% higher, a gym about 6%, and new construction since 2010 2 to 4%. These ranges are wider, and
the reason is instructive: doorman buildings also have bigger units with more washers, so how much of the gap belongs
to the doorman depends on whether you compare buildings as they are or buildings with the same mix of units.</p>
<p>Ads that say the unit is rent stabilized ask about 2.4% less, and income-restricted units about 10% less.</p>

<h2>Location is still mostly a map</h2>
<p>Where a building sits explains about a quarter of the spread in rents, more than any feature above. We'd love
to say exactly why: the subway, the parks, the river. So we tested it, by hiding about 6,800 buildings from the
model and asking whether knowing their distance to a station, a park or the water helped predict their rents.</p>
<p>Mostly it didn't. Distance to Central Park or Prospect Park does line up with rent, but the model's map already
knew that, because those parks are big and the map is drawn at about a kilometre's resolution. A feature that changes
more slowly than the map can't teach it anything new.</p>
<p>One feature did help: <b>a building directly facing a park of five acres or more</b>. Those buildings ask about
3.5% more (about $140 on our example) than nearby buildings that don't face the park, with a likely range of 2.6 to 4.3%. That
held up on buildings the model never saw, and when we planted a fake park premium in simulated rents, the model found
it. We're calling it provisional until it passes one more statistical test. Being right on the waterfront, by
contrast, looked great in training and made predictions worse for new waterfront buildings, so we dropped it.</p>

<h2>How sure are we?</h2>
<p>For a typical ad the model's middle guess is off by about 7%, and its 90% ranges contain the actual ask 90% of
the time, which is what they should do. We also tested the model on fake rents where we knew the right answers. It
recovered the map and the floor curve well. It overstated unit features by a fraction of a point, and its stated
uncertainty about individual features was too narrow, so we report ranges, not decimals.</p>
<h2>What we're modelling, and what's open</h2>
<p>Nobody publishes what New York tenants actually sign for, so we don't try to guess it. What we can observe is the
ask, and we treat the last ask before a listing goes off the market as the closest thing to a closing price: the
price at which the apartment found a taker. Every number above is about those prices.</p>
<p>Within that, the direction is wide open. The floor curve, the missing-square-footage discount and the park-facing
premium are the parts we can explain so far; the map that still carries a quarter of the variance is the part we
can't. If you have an idea about what in the observations would explain it, or a check that would break one of the
results above, that's what the comments are for.</p>
</section>

<footer>The model, data and every test behind this post are in the project's research notes from 21–22 October 2026. Dollar figures apply the percentage premiums to an illustrative $4,000 rent and are rounded.</footer>
</main>
"""

INIT = "floorChart('floor',ELEV,WALK);"

html = page(
    "Rent by the Floor",
    "Blog post on what apartment features add to New York asking rents",
    BODY,
    data_js() + INIT,
)
(HERE / "blog.html").write_text(html)
print(len(html))
