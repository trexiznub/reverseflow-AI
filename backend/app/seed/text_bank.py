"""Template banks for synthetic free text (return reasons, reviews, descriptions).

Texts are intentionally varied (synonyms, Hinglish, typos, mixed signals) so the
NLP classifier has to learn rather than pattern-match one phrase.
"""
from __future__ import annotations

import numpy as np

REASON_TEMPLATES = {
    "SIZE_SMALL": [
        "Ordered {size} but it is too tight around the waist",
        "Blouse is very tight, size runs small",
        "Size chhota hai, could not even close the hooks",
        "Fits at least one size smaller than the chart says",
        "Too tight at the bust, the {size} feels like a {smaller}",
        "Measurements don't match the size chart, way too snug",
        "choli too small, waist tight. size chart wrong",
        "Needed a bigger size, very tight fit after wearing once",
        "Small fitting, sleeves too narrow for {size}",
    ],
    "SIZE_LARGE": [
        "Too loose, {size} fits like a {bigger}",
        "Size is very big, kurta is hanging",
        "Length too long and loose at the shoulders",
        "Bada size aa gaya, too loose overall",
        "Oversized fit, need one size down",
        "waist is loose even after adjusting the dori",
    ],
    "STITCHING": [
        "Stitching came off after one wear, very poor finishing",
        "Loose stitching at the waistband, threads coming out",
        "Seam opened at the side during garba",
        "Silai bilkul kharab hai, thread nikal raha hai",
        "Blouse hem was unstitched when it arrived",
        "Poor stitching quality, the dupatta border is coming apart",
        "Side seam stitching loose, mirror work falling off",
        "stitches uneven and loose, looks handmade badly",
        "Kali panel stitch opened, not expected at this price",
    ],
    "COLOUR_MISMATCH": [
        "Colour is completely different from the photo",
        "Shade is much darker than shown on the website",
        "Expected {colour} but received a dull faded shade",
        "Rang alag hai, photo mein bright tha",
        "Colour mismatch, looks orange instead of pink",
        "The colour in the pictures is misleading",
    ],
    "FABRIC_QUALITY": [
        "Fabric feels cheap and rough, not silk as described",
        "Material quality is poor, very thin and see-through",
        "Fabric is itchy and the lining is synthetic",
        "Kapda bahut patla hai, quality not good",
        "Cloth started pilling after first use",
    ],
    "NOT_AS_DESCRIBED": [
        "Product looks different from the listing, embroidery missing",
        "Dupatta was not included though the listing says 3-piece set",
        "Design is not as shown, much simpler work",
        "Listing mentions mirror work, received plain print",
        "Not the same product as in the images",
    ],
    "DAMAGED_IN_TRANSIT": [
        "Package arrived torn and the outfit had a stain",
        "Box was wet and the lehenga got damaged",
        "Received with a tear near the hem, packaging damaged",
        "Product damaged during delivery, beads broken",
    ],
    "CHANGED_MIND": [
        "No longer needed",
        "Changed my mind, found another outfit for the event",
        "Event got over, don't need it now",
        "Bought two options, returning this one",
        "Not required anymore",
        "Didn't like it on me, want to return",
        "Plans changed, returning",
    ],
    "LATE_DELIVERY": [
        "Arrived after the function, no use now",
        "Delivery was late, missed the navratri night",
        "Came too late for the wedding",
        "Late delivery, occasion already over",
    ],
}

REVIEW_POSITIVE = [
    "Beautiful {cat_l}, the colour is exactly as shown. Loved wearing it.",
    "Fit was perfect and the fabric feels premium. Got many compliments.",
    "Lovely work, value for money. Will order again.",
    "Very comfortable for garba, the flare is great.",
    "Excellent quality and fast delivery. Highly recommend.",
    "Nice embroidery and true to size. Happy with the purchase.",
    "Superb finish, the mirror work is neat.",
    "Bahut sundar hai, fitting bhi achhi hai.",
]
REVIEW_NEUTRAL = [
    "Decent {cat_l} for the price, fabric could be better.",
    "Okay product, colour slightly different but acceptable.",
    "Average quality, delivery was fine.",
]
REVIEW_NEGATIVE = {
    "SIZE_SMALL": ["Size runs small, had to return. Please fix the size chart.", "Very tight fit, the chart is misleading.", "Ordered my usual size, way too small."],
    "SIZE_LARGE": ["Too loose for the size mentioned.", "Fit is oversized, not as per chart."],
    "STITCHING": ["Stitching opened on first wear. Poor quality control.", "Threads coming out everywhere, disappointed.", "Loose stitching, the seam came apart while dancing."],
    "COLOUR_MISMATCH": ["Colour totally different from pictures.", "Shade is dull, photos are edited."],
    "FABRIC_QUALITY": ["Fabric is cheap and thin.", "Not real silk, rough material."],
    "NOT_AS_DESCRIBED": ["Not as described, embroidery missing.", "Product doesn't match listing."],
    "DAMAGED_IN_TRANSIT": ["Arrived damaged, packaging was poor."],
    "CHANGED_MIND": ["It was fine but didn't suit me.", "Okay outfit, returned as plans changed."],
    "LATE_DELIVERY": ["Delivery too late for the festival.", "Late delivery ruined the plan."],
}

DESC = {
    "Lehenga": "{style} in {colour_l} {fabric_l} with a flared skirt, matching choli and dupatta. Hand-finished detailing. Dry clean only.",
    "Saree": "{style} in {colour_l} with contrast border and running blouse piece. 5.5 m saree + 0.8 m blouse.",
    "Kurta set": "{style} in {colour_l} {fabric_l}. Includes kurta, bottom and dupatta. Regular fit.",
    "Indo-western": "{style} in {colour_l} {fabric_l}. Contemporary silhouette with ethnic detailing.",
    "Festive dress": "{style} in {colour_l} {fabric_l}, lined, with concealed zip.",
}

SIZES = ["XS", "S", "M", "L", "XL", "XXL"]

# Vague free text customers often write; inspection later decides the real reason.
GENERIC = [
    "Not happy with the product", "Product not good", "Issue with the item, please take it back",
    "Didn't meet expectations", "Not satisfied", "Returning, quality and fit both not ok",
    "not as expected", "Item has problems", "Doesn't look good on me, fitting and finish average",
    "Want to return this", "Disappointed with purchase",
]
CONFUSABLE = {
    "SIZE_SMALL": "SIZE_LARGE", "SIZE_LARGE": "SIZE_SMALL", "STITCHING": "FABRIC_QUALITY", "FABRIC_QUALITY": "STITCHING",
    "COLOUR_MISMATCH": "NOT_AS_DESCRIBED", "NOT_AS_DESCRIBED": "COLOUR_MISMATCH", "CHANGED_MIND": "LATE_DELIVERY",
    "LATE_DELIVERY": "CHANGED_MIND", "DAMAGED_IN_TRANSIT": "STITCHING",
}
MIXED_REVIEWS = [
    "Looks good but the stitching is a bit loose at places.", "Lovely colour, but size runs small.",
    "Nice design, fabric not as soft as expected.", "Good value though fitting was slightly off.",
    "Beautiful work but delivery took long.",
]


def _pick(rng: np.random.Generator, lst):
    return lst[int(rng.integers(len(lst)))]


def reason_text(rng: np.random.Generator, reason: str, category: str, size: str) -> str:
    u = rng.random()
    if u < 0.13:
        return _pick(rng, GENERIC)
    if u < 0.20:
        reason = CONFUSABLE.get(reason, reason)  # customer describes it differently from what inspection finds
    t = _pick(rng, REASON_TEMPLATES[reason])
    i = SIZES.index(size) if size in SIZES else 2
    txt = t.format(size=size if size != "Free" else "free size", smaller=SIZES[max(i - 1, 0)], bigger=SIZES[min(i + 1, 5)],
                   colour="the listed colour")
    r = rng.random()
    if r < 0.12:
        txt = txt.lower()
    elif r < 0.18:
        txt += ". " + _pick(rng, ["Please arrange pickup.", "Want refund.", "Kindly exchange.", "Disappointed."])
    if rng.random() < 0.08:  # mixed signal: mention a second, minor issue
        txt += " Also " + _pick(rng, ["the colour is a bit off", "delivery was slow", "packaging was poor"])
    return txt


def review_text(rng: np.random.Generator, issue: str | None, category: str, returned: bool):
    cat_l = category.lower()
    if rng.random() < 0.10:
        return int(rng.choice([2, 3, 4])), _pick(rng, MIXED_REVIEWS), "mixed"
    if issue is None:
        r = rng.random()
        if r < 0.78:
            return int(rng.choice([4, 5], p=[0.4, 0.6])), _pick(rng, REVIEW_POSITIVE).format(cat_l=cat_l), "positive"
        return 3, _pick(rng, REVIEW_NEUTRAL).format(cat_l=cat_l), "neutral"
    bank = REVIEW_NEGATIVE.get(issue, REVIEW_NEUTRAL)
    rating = int(rng.choice([1, 2, 3], p=[0.45, 0.4, 0.15])) if issue not in {"CHANGED_MIND"} else int(rng.choice([3, 4], p=[0.6, 0.4]))
    return rating, _pick(rng, bank).format(cat_l=cat_l), issue.lower()


def product_description(category: str, style: str, colour: str, fabric: str) -> str:
    return DESC[category].format(style=style, colour_l=colour.lower(), fabric_l=fabric.lower())
