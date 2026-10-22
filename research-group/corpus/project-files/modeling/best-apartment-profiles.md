# Playtester profiles: how each would weight the model's features

Draft for Ben, 2026-10-06. Taste items are left out: neighbourhood, era, landmark and historic district, views and window direction, fireplace, building size and the luxury-building proxy.

Bedroom count and income restriction are treated as filters, not preferences.

## Profiles
- **Solo:** a young professional living alone who commutes. Wants convenience and some polish.
- **Family:** a couple with a toddler and a stroller. Needs space and an easy entrance.
- **Sharers:** two or three roommates splitting rent. Price comes first, and they need real bedrooms and enough bathrooms.
- **Older:** a retired couple. Stairs are a problem, and they value staff and quiet.
- **WFH:** a remote worker home all day. Needs light, quiet and a room to work in.

## Scale and columns
- Scale: ++ strong pro, + pro, 0 neutral, − con, −− strong con.
- Market: the sign of the served model's coefficient, meaning what the market charges for the feature.

| Feature | Market | Solo | Family | Sharers | Older | WFH |
|---|---|---|---|---|---|---|
| **Space** | | | | | | |
| Larger than typical for its bedroom count | + | + | ++ | + | + | + |
| Extra full bathroom | + | 0 | + | ++ | + | + |
| Half bath | + | 0 | + | + | 0 | 0 |
| Extra room beyond the bedrooms | + | + | + | + | 0 | ++ |
| Duplex (stairs inside) | + | + | − | + | −− | + |
| Ad lists fewer bedrooms than coded (converted room) | − | 0 | − | −− | 0 | − |
| **Floor and position** | | | | | | |
| Higher floor, with an elevator | + | + | 0 | 0 | + | + |
| Higher floor in a walk-up | − | − | −− | − | −− | − |
| Penthouse | + | + | 0 | 0 | + | + |
| Lower level | − | − | − | 0 | − | −− |
| Garden unit | + | 0 | ++ | 0 | + | 0 |
| Low floor on an avenue or wide street | − | 0 | − | 0 | − | −− |
| Rear or courtyard facing | + | 0 | + | 0 | + | ++ |
| **Outdoor** | | | | | | |
| Private outdoor space | + | + | ++ | + | + | + |
| Shared roof deck | + | + | 0 | + | 0 | + |
| **Unit** | | | | | | |
| In-unit laundry | + | + | ++ | + | + | + |
| Dishwasher | + | + | + | + | 0 | + |
| Renovated | + | + | + | + | + | + |
| **Building** | | | | | | |
| Elevator | + | + | ++ | 0 | ++ | + |
| Doorman | + | + | + | 0 | ++ | + |
| Gym in building | − | + | 0 | 0 | 0 | + |
| Walk-up class (small, older) | − | 0 | − | 0 | −− | 0 |
| Mixed use, retail below | − | 0 | − | 0 | − | − |
| Dense lot | − | 0 | 0 | 0 | 0 | − |
| **Deal terms** | | | | | | |
| Concession or no fee | − | + | + | ++ | + | + |
| Rent stabilized | − | ++ | ++ | ++ | ++ | ++ |
| Furnished | + | + | − | 0 | − | 0 |
| Short-term lease | − | 0 | −− | − | − | − |
| **Hidden quality** | | | | | | |
| Building persistently below its features | − | − | − | 0 | − | − |
| Unit below its building | − | − | − | − | − | − |
| Building trending down vs the market | − | − | − | 0 | − | − |

## What the grid shows
- **Biggest disagreements:** stairs, ground level and how much space matters. Duplex, garden, walk-up floors and elevator split the profiles most.
- **Deal terms are pros for everyone,** even though the market sign is negative. This is where price and preference diverge most.
- **Sharers vs Older:** Sharers barely care about the building and focus on bathrooms, real bedrooms and price. The older couple is the reverse.
- **Hidden building quality:** Sharers get 0 because a cheap building is mostly good news for them. For everyone else a building persistently below its features is a con.

## How it combines with the model
For each listing:

profile score = Σ weight (++ = 2 … −− = −2) × |coefficient| × feature value

- **Uncertainty:** the score is computed for every posterior draw, so each score has an interval.
- **Roles:** the model sets the size of each feature, and the profile sets its sign and emphasis.
- **Best value:** the score minus log rent.

## Next step
Before anything goes on the site, the playtester agents fill in the grid blind to check these calls.
