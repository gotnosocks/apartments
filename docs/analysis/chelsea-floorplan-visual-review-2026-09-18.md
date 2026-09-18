# Chelsea bathroom-access floor-plan pilot

Four images were acquired through Oxylabs from exact floor-plan references in the
archived advertisements. Two independent visual reviews agree on the findings
below. This establishes what the diagrams depict, not the actual construction or
the validity of a historical layout.

| Advertisement | Diagram access | Fixture evidence |
|---|---|---|
| 1639871, Loft 25 6H | One suite bath through its dressing area; one hall bath | Two full baths |
| 4068484, 248 Tenth Avenue 2B | One suite bath; one common-access bath | Fixtures omitted; full/half unknown from image |
| 3059501, 520 West 28th 0007 | Likely two suite baths; exact count withheld because door details are faint | Two full baths **plus powder room** |
| 3213567, Chelsea Stratus 23B | One suite bath; one hall bath | Two full baths |

The second advertisement says each bedroom has its own bathroom. Its diagram
illustrates why assigned private use does not establish an attached bathroom.
The third image both labels and draws a powder room, contradicting the structured
two-full/zero-half inventory. It therefore cannot supply a clean one-versus-two
en-suite comparison at fixed fixture counts. The fourth also labels its second
room DEN/BEDROOM; the source describes sliding glass doors to the living room.
Bathroom access and bedroom separation should remain distinct research features.

No source counts, analytical rows, or model fits were changed by this review.
The uncertain two-suite interpretation is stored as a possible count with the
exact count null. The unlabeled 248 Tenth Avenue image remains bound only by its
same-advertisement reference, without an independently visible address/unit label.

Acquisition: `data/probes/chelsea-floorplans-20260918`, four submissions, four
successful images, no retries. Each asset retains its provider response, image
hash, new collection timestamp, and archived-reference ancestry. The bytes were
collected on September 18; an older HTML reference does not prove these same bytes
were available at that earlier capture time.

Authoritative visual review:
`data/model/chelsea-floorplan-visual-review-20260918-v2`. The initial v1 reading is
retained, with v2 explicitly withholding the ambiguous exact suite count and
recording agreement of the independent review. Both are research annotations.

Implementation: `models/fetch_floorplan_assets.py`. Nine tests cover supported
image formats, rejected failures/non-images, URL restrictions, completed replay
without a second request, and refusal to retry uncertain submissions. The live
completed acquisition and final review replayed without new requests or changes.
The report/floor-plan focused suite passes 24 tests.
