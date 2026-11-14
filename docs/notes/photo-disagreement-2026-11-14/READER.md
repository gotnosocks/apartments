# Reading an apartment's photos and floor plan

You read the images of a batch of New York rental apartments. Each apartment has a label
such as P042 and a folder of images: photos `p01.jpg`, `p02.jpg` and so on, in the order the
ad showed them, and `plan.jpg` when the ad had a floor plan. The batch file gives each
label's bedrooms, baths and borough. You know nothing else about the apartment, and you
should not look for anything else: open no file outside the batch file and the image
folders of your labels.

Look at every image of an apartment with the Read tool before you judge it. Judge each
apartment from its own images, and don't compare it with the others in your batch. Judge
what a renter browsing the ad would see. A folder with no images gets `"photos": 0`, an empty
category list and null grades.

## Categories

Mark every category that applies. Mark a category when the images show it, and leave it
unmarked when you would be guessing.

- `dark_or_shaft`: the rooms are dim in daylight photos, or a window faces a shaft, a wall or
  a court a few feet away.
- `low_ceiling`: the ceiling is visibly low, under about 8 feet, or beams and soffits cut
  the height.
- `awkward_layout`: the plan or the photos show a railroad layout, rooms entered through
  other rooms, a long dark hall, odd angles, or a bed in the living room of a unit with 1 or
  more bedrooms.
- `tiny_or_windowless_bedroom`: a bedroom holds little beyond the bed, or has no window, or
  only an interior window.
- `kitchen_poor`: the kitchen is worn or dated, or is a kitchenette along a wall of the
  living room with small appliances.
- `bath_poor`: the bath is worn or dated: old tile, stained grout, an old tub or vanity.
- `worn_finishes`: floors, walls, doors or windows are worn or damaged over the whole unit.
- `ground_or_basement`: the photos or the plan show a unit at or below the street: bars on
  windows, sidewalk-level views, window wells, a cellar level.
- `street_noise_cues`: windows give on an avenue, a highway, an elevated train, a bar front
  or a construction site.
- `other_unit_or_renderings`: the images are renderings, a model unit, photos marked as
  another unit, or building and amenity shots with no photo of the unit itself. Virtually
  staged furniture in a real photo of the unit does not count.

When none applies, give an empty list.

## Grades

Give each grade as a whole number from 1 to 5. Give null when the images cannot support the
grade, as with renderings alone or no interior photo.

Condition, over the whole unit:

1. Worn or damaged.
2. Dated: old kitchen and bath, tired floors, serviceable.
3. Ordinary and sound: clean, plain, some updates.
4. Renovated: a recent renovation of the kitchen and bath, floors in very good condition.
5. New or high end: new construction or premium finishes throughout.

Light, in the living spaces:

1. Dark: little daylight reaches the rooms.
2. Dim: small or blocked windows.
3. Ordinary.
4. Bright: good windows, daylight across the rooms.
5. Very bright: large windows or window walls, open sky.

## What to write

Write one JSON line for each apartment of your batch to the output file named in your
instructions, and nothing else in that file:

```json
{"label": "P042", "photos": 8, "plan": true, "categories": ["kitchen_poor", "dark_or_shaft"], "condition": 2, "light": 2, "note": "old laminate kitchen in p03; bedroom window on a brick wall in p05"}
```

`photos` is the number of photos you looked at, `plan` says whether you looked at a plan,
and `note` is a short phrase pointing at the images behind your marks.
