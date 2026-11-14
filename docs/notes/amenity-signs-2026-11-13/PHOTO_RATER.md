# Rating an apartment's photos

You rate the photos of a few New York rental apartments. Each apartment has a label such as
A07 and a folder of photos, `p01.jpg`, `p02.jpg` and so on, in the order the ad showed them.
Look at every photo of an apartment with the Read tool before you rate it. Rate each
apartment on its own photos alone, and don't compare it with the others in your batch.

Rate four things on a scale from 1 to 5, where a higher number means newer or better. Leave a
rating as null when no photo shows the thing, and don't guess it from the other photos. When
a room shows in several photos, rate what most of them show.

## The kitchen's finish

1. Worn or dated: old cabinets, laminate or tile counters, old appliances, visible wear.
2. Plain and older: serviceable builder-grade cabinets and counters, clearly not recent.
3. Updated in part: some recent work, such as newer appliances or counters, the rest basic.
4. Renovated: a recent full renovation, with stone counters, newer cabinets and stainless
   appliances.
5. New and high end: custom or premium cabinetry, premium appliances, designer finishes.

## The bath's finish

1. Worn or dated: old tile, an old tub or vanity, stained grout, visible wear.
2. Plain and older: serviceable fixtures and tile, clearly not recent.
3. Updated in part: a newer vanity or fixtures, the rest basic.
4. Renovated: new tile, vanity and fixtures throughout.
5. New and high end: premium stone or tile, designer fixtures, a glass shower or a soaking
   tub.

## The floors

1. Damaged or worn, or old carpet, vinyl or linoleum.
2. Plain and older: dull or scuffed wood, basic tile, laminate.
3. Sound and ordinary: wood or laminate in good repair.
4. Refinished or new wood in very good condition.
5. Premium: wide-plank or patterned wood, or stone, in fine condition.

## The building's apparent age

Judge the decade the building went up from the exterior, the lobby, the halls, the windows
and the room details such as moldings, ceiling height and radiators.

1. Before 1900: a tenement, brownstone or row house.
2. 1900 to 1939: a prewar walk-up or elevator building.
3. 1940 to 1979: a postwar building, often white or red brick with an elevator.
4. 1980 to 2009.
5. 2010 or later: new construction.

## What to write

Write one JSON line for each apartment to the output file named in your instructions:

```json
{"label": "A07", "photos": 9, "kitchen": 3, "bath": null, "floors": 4, "building_age": 2, "note": "no bath photo; prewar facade in p01"}
```

`photos` is the number of photos you looked at. `note` is a short phrase naming the photos
behind the ratings or saying why one is null. Write nothing else in the file.
