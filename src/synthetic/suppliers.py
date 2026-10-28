"""Fictional company and supplier registry for synthetic data generation.

All identifiers here (NIFs, VAT numbers, IBANs) are deliberately fake —
they use obviously-invalid patterns (lots of zeros) so secret scanners
and human readers can tell at a glance that nothing here is real.
"""
from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class Company:
    canonical_name: str
    country: str
    address: str
    tax_id: str
    iban: str
    language: str  # "en" | "es" | "ca"
    category: str
    name_variants: tuple[str, ...] = field(default_factory=tuple)


# Our fictional business — the recipient of every supplier invoice below.
OUR_COMPANY = Company(
    canonical_name="Costa Brava Studio S.L.",
    country="ES",
    address="Carrer de l'Exemple, 12, 08001 Barcelona",
    tax_id="B00000001",
    iban="ES00 0000 0000 0000 0000 0001",
    language="ca",
    category="",
)

SUPPLIERS: dict[str, Company] = {
    "notion": Company(
        canonical_name="Notion Labs, Inc.",
        country="US",
        address="000 Fictional Ave, Suite 000, San Francisco, CA 00000",
        tax_id="00-0000001",
        iban="",
        language="en",
        category="Software & Subscriptions",
        name_variants=("Notion Labs Inc", "NOTION LABS", "Notion Labs, Inc"),
    ),
    "adobe": Company(
        canonical_name="Adobe Inc.",
        country="IE",
        address="000 Fictional Quay, Dublin 0, Ireland",
        tax_id="IE0000000A",
        iban="IE00 0000 0000 0000 0000 00",
        language="en",
        category="Software & Subscriptions",
        name_variants=("ADOBE SYSTEMS SOFTWARE IRELAND LTD",),
    ),
    "figma": Company(
        canonical_name="Figma, Inc.",
        country="US",
        address="000 Fictional St, San Francisco, CA 00000",
        tax_id="00-0000002",
        iban="",
        language="en",
        category="Software & Subscriptions",
    ),
    "coworking": Company(
        canonical_name="Barcelona Working Hub, S.L.",
        country="ES",
        address="Carrer de la Diputació, 211, 08011 Barcelona",
        tax_id="B00000002",
        iban="ES00 0000 0000 0000 0000 0002",
        language="es",
        category="Coworking & Office Space",
    ),
    "electricity": Company(
        canonical_name="Energia Costa Brava, S.L.",
        country="ES",
        address="Avinguda Jaume I, 45, 17001 Girona",
        tax_id="B00000003",
        iban="ES00 0000 0000 0000 0000 0003",
        language="es",
        category="Utilities",
    ),
    "internet": Company(
        canonical_name="Fibra Catalana, S.L.",
        country="ES",
        address="Carrer Nou, 22, 17600 Figueres",
        tax_id="B00000004",
        iban="ES00 0000 0000 0000 0000 0004",
        language="ca",
        category="Utilities",
    ),
    "freelancer": Company(
        canonical_name="Jordi Soler Fotografia",
        country="ES",
        address="Carrer Ample, 5, 17004 Girona",
        tax_id="00000000A",
        iban="ES00 0000 0000 0000 0000 0005",
        language="ca",
        category="Professional Services",
    ),
    "printer": Company(
        canonical_name="Impremta Girona, S.L.",
        country="ES",
        address="Carrer de la Força, 8, 17004 Girona",
        tax_id="B00000005",
        iban="ES00 0000 0000 0000 0000 0006",
        language="ca",
        category="Printing & Supplies",
    ),
    "nordic": Company(
        canonical_name="Nordic Design Tools GmbH",
        country="DE",
        address="Fiktionstraße 0, 00000 Berlin, Germany",
        tax_id="DE000000000",
        iban="DE00 0000 0000 0000 0000 00",
        language="en",
        category="Software & Subscriptions",
    ),
    "studiofonts": Company(
        canonical_name="Studio Fonts France SARL",
        country="FR",
        address="0 Rue Fictive, 00000 Paris, France",
        tax_id="FR00000000000",
        iban="FR00 0000 0000 0000 0000 0000 000",
        language="en",
        category="Software & Subscriptions",
    ),
    "pixelco": Company(
        canonical_name="Pixel & Co Design Ltd",
        country="GB",
        address="0 Fictional Lane, London, EC0 0AA, United Kingdom",
        tax_id="GB000000000",
        iban="GB00 FAKE 0000 0000 0000 00",
        language="en",
        category="Professional Services",
    ),
    "cloudhost": Company(
        canonical_name="CloudHost Barcelona, S.L.",
        country="ES",
        address="Carrer de Pallars, 99, 08018 Barcelona",
        tax_id="B00000006",
        iban="ES00 0000 0000 0000 0000 0007",
        language="es",
        category="Software & Subscriptions",
    ),
    "courier": Company(
        canonical_name="Missatgeria Girona, S.L.",
        country="ES",
        address="Carrer Barcelona, 60, 17002 Girona",
        tax_id="B00000007",
        iban="ES00 0000 0000 0000 0000 0008",
        language="ca",
        category="Shipping & Courier",
    ),
    "insurance": Company(
        canonical_name="Assegurances Costa Brava, S.L.",
        country="ES",
        address="Rambla de Girona, 2, 17001 Girona",
        tax_id="B00000008",
        iban="ES00 0000 0000 0000 0000 0009",
        language="ca",
        category="Insurance",
    ),
    "furniture": Company(
        canonical_name="Mobles Office BCN, S.L.",
        country="ES",
        address="Carrer de la Marina, 16, 08005 Barcelona",
        tax_id="B00000009",
        iban="ES00 0000 0000 0000 0000 0010",
        language="es",
        category="Office Supplies",
    ),
    "catering": Company(
        canonical_name="Café Central",
        country="ES",
        address="Plaça Catalunya, 1, 08002 Barcelona",
        tax_id="B00000010",
        iban="ES00 0000 0000 0000 0000 0011",
        language="es",
        category="Meals & Entertainment",
    ),
    "officesupplies": Company(
        canonical_name="Toner & Papereria Girona",
        country="ES",
        address="Carrer Santa Clara, 14, 17001 Girona",
        tax_id="B00000011",
        iban="ES00 0000 0000 0000 0000 0012",
        language="ca",
        category="Office Supplies",
    ),
    "travel": Company(
        canonical_name="Viatges Business, S.L.",
        country="ES",
        address="Carrer Pelai, 30, 08001 Barcelona",
        tax_id="B00000012",
        iban="ES00 0000 0000 0000 0000 0013",
        language="ca",
        category="Travel",
    ),
    "accounting": Company(
        canonical_name="Assessoria Fiscal Puig & Associats",
        country="ES",
        address="Gran Via de les Corts Catalanes, 500, 08015 Barcelona",
        tax_id="B00000013",
        iban="ES00 0000 0000 0000 0000 0014",
        language="es",
        category="Accounting & Legal",
    ),
}
