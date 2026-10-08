---
title: Japanese design defaults
summary: Real-world buildings, products, equipment and everyday items follow Japanese specifications, design and standards unless the user names another country or region - how to work out the Japanese version of anything, with examples from housing, electrical fittings, roads, vehicles and everyday items.
---

# Japanese design defaults

## The rule

When the user names no country or region, model real-world buildings, products, equipment and
everyday items to Japanese specifications, design and standards. When the user names another
country or region, follow that instead. A setting that clearly implies a place ("a New York
diner", "a London bus stop") counts as naming it. Fantasy, sci-fi and stylised worlds have no
real-world standard to follow; use Japanese defaults only for the everyday objects in them.

Apply it to the details as well as the big picture: an otherwise convincing room reads as foreign
when its sockets, doors or signs are from somewhere else.

## Applying it to anything

The sections below are examples, not the limit of the rule. For any real-world thing, listed or
not (a school desk, a hospital bed, a train interior, a konbini shelf, a fire extinguisher), work
out the Japanese version before modelling it:

1. **Ask what it looks like in Japan.** Picture the version sold, built or installed there today,
   not the one common in American or European media and stock assets, which most models and
   library assets default to.
2. **Standards and law.** Many things are fixed by JIS (Japanese Industrial Standards), the
   Building Standards Act, the Road Traffic Act and similar rules: sizes, colours, symbols,
   markings, placement. Use those numbers where you know them; where you don't, use a typical
   Japanese size and say it is approximate.
3. **Units and sizes.** Metric, with traditional modules in construction (910 mm, tatami). Japanese
   homes, cars and appliances run smaller and more compact than American ones.
4. **Language and markings.** Labels, signs, buttons, packaging and screens are in Japanese; warning
   and safety markings follow Japanese conventions.
5. **Habits and climate.** Shoes off indoors, separate bath and toilet, futons and low tables in
   washitsu, sliding doors, wet seasons and snow in the north: these decide what is present and
   where it goes.
6. **Library and generated assets.** Most are American or European. Check each against the points
   above: replace or edit what gives the wrong country away (sockets, plates, signs, steering side,
   text), and prompt `generate_3d` for the Japanese version explicitly ("Japanese ...").

When the Japanese version is genuinely unclear or varies a lot (by maker, era or region), pick the
most common current one and tell the user which you assumed.

## Examples: houses and interiors

- Planning grid: 910 mm (shaku module); walls, corridors and stairs line up with it.
- Tatami about 910 x 1820 mm (sizes vary by region, 880-955 mm wide); rooms are counted in mats
  (6-jo, 8-jo). A washitsu has tatami, fusuma and shoji sliding doors, and a tokonoma alcove.
- Genkan: shoes come off at a step up (agari-kamachi) of roughly 100-300 mm, with a shoe cabinet.
- Ceilings about 2.4 m in homes; interior doors about 2.0 m high, 750-800 mm wide; sliding doors
  are common.
- Bathroom: the bath is a separate room from the toilet, with a deep tub and a washing area with a
  shower and stool beside it (a modular "unit bath"); the washbasin and washing machine sit in a
  changing room outside it. Toilets have a bidet seat (washlet) with a side control panel.
- Kitchen counters about 850 mm high; dining tables about 700 mm.
- Stairs in houses: risers up to 230 mm, treads at least 150 mm (Building Standards Act minimums;
  real houses are gentler, around 200 / 220 mm).

## Examples: electrical and fittings

- 100 V. Sockets are type A (two flat parallel slots), usually a duplex in a white plate, many
  with a third, grounding hole in kitchens and wet rooms. Switches are wide rocker plates.
- Ceiling lights hang from a round ceiling rosette (hikkake sealing) rather than wired fixtures.
- Air conditioners are wall-mounted split units high on the wall, with the outdoor unit and its
  pipe cover outside.

## Examples: streets, roads and traffic

- Traffic drives on the left; cars are right-hand drive. Pedestrian crossings are zebra stripes
  without a centre line on the road.
- Traffic lights are horizontal with green-blue, yellow and red lamps; pedestrian signals are
  separate, with walking and standing figures.
- Stop signs are a downward red triangle reading 止まれ. Regulatory signs are round (blue or
  red-ringed), warning signs yellow diamonds. Road text is in Japanese.
- Utility poles and overhead wires line most streets; drain covers have grated lids at the kerb.
- Street furniture: red cylindrical or box post boxes with 〒, vending machines (often in rows,
  lit at night), convenience stores with bright signage, guardrails at road edges.

## Examples: vehicles and transport

- Number plates: white with green text for private cars, yellow with black for kei cars, the
  region name and hiragana on the plate. Kei cars are boxy and narrow (under 1.48 m wide).
- Taxis have a roof sign and automatic rear left door. Bicycles are often step-through city bikes
  with a front basket.
- Conventional railways are mostly 1067 mm gauge; the Shinkansen uses 1435 mm.

## Examples: everyday items

- Paper sizes A4 and B5 (JIS B, slightly larger than ISO B). Money is yen; coins 1-500 yen.
- Writing and labels on products, packaging and signs are Japanese (kanji, kana), with
  horizontal text on signage and products and vertical text where tradition calls for it
  (shop curtains, some book spines, signboards).
