"""Facebook titles -> clean page titles. Cases are Ali Abbas' real listing titles."""
import pytest

from scraper.titles import clean_title, plain_text


@pytest.mark.parametrize("raw,clean", [
    ("☕ De’LONGHI MAGNIFICA EVO – AUTOMATIC ESPRESSO & COFFEE MACHINE\n\n✨ NEW OPEN BOX – FULLY TESTED & REA",
     "De'Longhi Magnifica Evo – Automatic Espresso & Coffee Machine"),
    ("\U0001F916 ECOVACS DEEBOT N30 PRO OMNI – ADVANCED ROBOT VACUUM & MOP", "Ecovacs Deebot N30 Pro Omni – Advanced Robot Vacuum & Mop"),
    ("DeLonghi Ceramic Tower Heater-New Open Box", "De'Longhi Ceramic Tower Heater-New Open Box"),
    ("De'Longhi Magnifica Start Automatic Espresso Coffee Machine- New open box",
     "De'Longhi Magnifica Start Automatic Espresso Coffee Machine – New open box"),
    ("\U0001F525 NINJA DELUXE KITCHEN SYSTEM – POWERFUL ALL-IN-ONE KITCHEN MACHINE! \U0001F525\n\n\U0001F4A5 ONE MACHINE – ENDLESS P",
     "Ninja Deluxe Kitchen System – Powerful All-in-One Kitchen Machine"),
    ("\U0001F4A5Nespresso CitiZ Platinum Espresso Machine \U0001F4A5 It’s  \U0001F4AF % Brand New",
     "Nespresso CitiZ Platinum Espresso Machine It's 100% Brand New"),
    ("\U0001F525 ECOVACS X2 OMNI ROBOT VACUUM & MOP – NEW OPEN BOX! \U0001F525with replacement warranty of 15 days \U0001F4A5",
     "Ecovacs X2 Omni Robot Vacuum & Mop – New Open Box with replacement warranty of 15 days"),
    ("\U0001F525 HOOVER CORDLESS STICK VACUUM – NEW open BOX! \U0001F525", "Hoover Cordless Stick Vacuum – New Open Box"),
    ("\U0001F343 STEELITE CORDLESS LEAF BLOWER – 20V | BATTERY & CHARGER INCLUDED! \U0001F343\n\nKeep your yard",
     "Steelite Cordless Leaf Blower – 20V | Battery & Charger Included"),
    ("\U0001F525 ECOVACS TEO / T20 OMNI ROBOT VACUUM & MOP – 100% BRAND NEW! \U0001F525", "Ecovacs TEO / T20 Omni Robot Vacuum & Mop – 100% Brand New"),
    ("Emma Hybrid Comfort Twin XL Mattress\n\nBrand New - Never Open", "Emma Hybrid Comfort Twin XL Mattress"),
    ("Cosco Kids Finale 2-in-1 Booster Car Seat", "Cosco Kids Finale 2-in-1 Booster Car Seat"),
    ("Hoover CleanSlate Pet+ Carpet & Upholstery Spot Cleaner", "Hoover CleanSlate Pet+ Carpet & Upholstery Spot Cleaner"),
    ("Ecovacs Deebot T10+ Robot Vacuum and Mop - COMPANY SEALED NEVER OPENED BOX",
     "Ecovacs Deebot T10+ Robot Vacuum and Mop - Company Sealed Never Opened Box"),
    ("", ""),
])
def test_clean_title(raw, clean):
    assert clean_title(raw) == clean


def test_clean_title_never_leaves_emoji_or_double_spaces():
    out = clean_title("\U0001F525\U0001F525  SAMSUNG  55”  4K TV ⭐️ LIKE NEW!! \U0001F525")
    assert out == "Samsung 55” 4K TV Like New" and "  " not in out


def test_plain_text_makes_one_clean_line():
    assert plain_text("\U0001F525 Great deal!\n\n✅ Works   well .", 200) == "Great deal! Works well."
    assert plain_text("word " * 100, 50).endswith("…") and len(plain_text("word " * 100, 50)) <= 50


@pytest.mark.parametrize("raw,clean", [
    ("Message us today!\n\nThe Goods Lane by Abbottcom\nQuality Products.", "Message us today!\n\nThe Goods Lane\nQuality Products."),
    ("⭐ THE GOODS LANE BY ABBOTTCOM\nGreat value", "⭐ THE GOODS LANE\nGreat value"),
    ("The Goods Lane by Abbott Com", "The Goods Lane"),
    ("Sold by AbbottCom, Mississauga", "Sold, Mississauga"),
    ("Abbott and Costello box set", "Abbott and Costello box set"),
    ("Stand by me", "Stand by me"),
])
def test_company_name_is_dropped_from_listing_text(raw, clean):
    from scraper.titles import drop_company_name
    assert drop_company_name(raw) == clean
