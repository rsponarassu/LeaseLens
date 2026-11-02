"""The three demo leases.

These are synthetic documents written for the demo. Each one is deliberately built
around a different risk profile so that the product can be shown end to end:

* ``sample-high-deposit``  - aggressive landlord draft (critical)
* ``sample-moderate-rent`` - a typical Chennai agreement with three rough edges (elevated)
* ``sample-tenant-friendly`` - a well-drafted agreement (low)

The text is authored so that the deterministic extractor finds every value, which
keeps the demo (and the tests) independent of any LLM.
"""

from __future__ import annotations

from dataclasses import dataclass

from app.models.enums import RiskLevel


@dataclass(frozen=True)
class SampleLeaseSpec:
    """Everything needed to render and describe a demo lease."""

    sample_id: str
    title: str
    tenant_persona: str
    property_description: str
    scenario: str
    expected_risk_level: RiskLevel
    monthly_rent_inr: int
    parties: tuple[tuple[str, str], ...]
    preamble: tuple[str, ...]
    clauses: tuple[tuple[str, str], ...]
    expected_min_violations: int = 1


HIGH_RISK = SampleLeaseSpec(
    sample_id="sample-high-deposit",
    title="Chennai - Adyar 2BHK, aggressive landlord draft",
    tenant_persona="Software engineer relocating to Chennai, first independent rental",
    property_description="2BHK apartment, 1,050 sq ft, Adyar, Chennai 600020",
    scenario=(
        "A broker-forwarded draft with a ten-month deposit, an eighteen-month lock-in "
        "and a seven-day notice period. The tenant has already been asked to transfer "
        "the deposit before signing."
    ),
    expected_risk_level=RiskLevel.CRITICAL,
    monthly_rent_inr=35000,
    parties=(
        ("Landlord", "Mr. S. Rajagopal, No. 12, Kasturba Nagar, Adyar, Chennai 600020"),
        ("Tenant", "Ms. A. Priyadarshini, presently at No. 44, Besant Nagar, Chennai 600090"),
        ("Premises", "First floor, Flat 1B, No. 12, Kasturba Nagar, Adyar, Chennai 600020"),
    ),
    preamble=(
        "This Rental Agreement is made on this 24th day of November 2026 between the "
        "Landlord and the Tenant named above, on the terms recorded below.",
    ),
    clauses=(
        (
            "Term of Tenancy",
            "The tenancy shall be for a fixed period of 22 months commencing on 1 December 2026 "
            "and ending on 30 September 2028, unless terminated earlier in accordance with this "
            "Agreement.",
        ),
        (
            "Security Deposit",
            "The Tenant shall pay to the Landlord an interest free security deposit of "
            "Rs. 3,50,000/- being equivalent to ten months rent, simultaneously with the "
            "execution of this Agreement. The said security deposit is non-refundable and "
            "shall stand forfeited in full if the Tenant vacates the premises before the "
            "expiry of the lock-in period.",
        ),
        (
            "Refund of Security Deposit",
            "The Landlord shall refund the security deposit within 60 days from the date on "
            "which the Tenant vacates the premises, after deducting arrears of rent, electricity "
            "charges and the cost of repairing any damage caused to the premises.",
        ),
        (
            "Lock-in Period",
            "There shall be a lock-in period of 18 months from the date of commencement of "
            "tenancy. In the event the Tenant terminates this Agreement during the lock-in "
            "period, the Tenant shall pay to the Landlord a penalty equivalent to six months "
            "rent, in addition to any other amount due under this Agreement.",
        ),
        (
            "Rent and Revision",
            "The monthly rent shall be Rs. 35,000/- payable on or before the fifth day of every "
            "English calendar month. The Landlord may increase the rent by 15% every 11 months, "
            "at his sole discretion, without the consent of the Tenant, by giving intimation in "
            "writing.",
        ),
        (
            "Notice of Termination",
            "The Tenant shall give 7 days written notice to the Landlord before vacating the "
            "premises. The Landlord may terminate this Agreement immediately and re-enter the "
            "premises without any further notice if he so desires.",
        ),
        (
            "Entry and Inspection",
            "The Landlord, his agents or representatives shall have the right to enter the "
            "premises at any time without prior notice for the purpose of inspection, repair or "
            "showing the premises to prospective tenants or purchasers.",
        ),
        (
            "Repairs and Maintenance",
            "The Tenant shall be responsible for all repairs and maintenance of the premises "
            "including structural repairs to the roof, walls, plumbing lines and electrical "
            "wiring. The Landlord shall have no obligation to carry out any repairs during the "
            "subsistence of this tenancy.",
        ),
        (
            "Electricity and Water Charges",
            "The Tenant shall pay electricity and water charges as per actual consumption. The "
            "Landlord shall be entitled to disconnect the water supply and electricity if the "
            "rent remains unpaid for seven days from the due date.",
        ),
        (
            "Registration",
            "This Agreement shall not be registered with the Rent Authority and the Tenant shall "
            "bear all stamp duty and incidental charges, if any.",
        ),
        (
            "Original Agreement",
            "The Landlord shall retain the original signed agreement and shall furnish only a "
            "photocopy thereof to the Tenant for his records.",
        ),
        (
            "Payment of Rent and Receipt",
            "The Tenant shall pay the monthly rent on or before the fifth day of each calendar "
            "month by bank transfer to the account nominated by the Landlord. The Landlord shall "
            "issue a written receipt for every payment received.",
        ),
        (
            "Inventory",
            "The premises are let with two ceiling fans, two air conditioners, one geyser, a "
            "modular kitchen and wardrobes in both bedrooms, all of which are in working "
            "condition on the date of handing over.",
        ),
        (
            "Governing Law and Jurisdiction",
            "This Agreement shall be governed by the laws of India and the parties agree to "
            "submit to the exclusive jurisdiction of the civil courts at Chennai.",
        ),
    ),
    expected_min_violations=8,
)


ELEVATED_RISK = SampleLeaseSpec(
    sample_id="sample-moderate-rent",
    title="Chennai - Velachery 2BHK, typical broker draft",
    tenant_persona="Marketing manager renewing a lease for a second year",
    property_description="2BHK apartment, 900 sq ft, Velachery, Chennai 600042",
    scenario=(
        "A standard broker-prepared agreement. The deposit is within the statutory limit, but "
        "the refund window, the entry notice and the rent-revision notice are all shorter than "
        "the Act's benchmarks - three terms to renegotiate, none of them fatal."
    ),
    expected_risk_level=RiskLevel.ELEVATED,
    monthly_rent_inr=28000,
    parties=(
        ("Landlord", "Mrs. K. Vasanthi, No. 8, Vijay Nagar, Velachery, Chennai 600042"),
        ("Tenant", "Mr. D. Arunkumar, No. 21, Anna Nagar West, Chennai 600040"),
        ("Premises", "Second floor, Flat 2C, No. 8, Vijay Nagar, Velachery, Chennai 600042"),
    ),
    preamble=(
        "This Rental Agreement is executed on 2 December 2026 between the parties named above "
        "for the residential premises described above.",
    ),
    clauses=(
        (
            "Period of Tenancy",
            "The tenancy shall commence on 1 January 2027 and shall be for a period of 11 "
            "months, renewable by mutual consent in writing.",
        ),
        (
            "Security Deposit",
            "The Tenant has paid an interest free security deposit of Rs. 84,000/- equal to "
            "three months rent, receipt whereof the Landlord hereby acknowledges. The deposit "
            "is refundable subject to the Tenant clearing all dues.",
        ),
        (
            "Refund of Deposit",
            "The security deposit shall be returned to the Tenant within 45 days after the "
            "Tenant vacates the premises and hands over possession, after adjusting any arrears "
            "of rent and charges for damages beyond normal wear and tear.",
        ),
        (
            "Lock-in Period",
            "There shall be a lock-in period of 11 months. If the Tenant vacates the premises "
            "before the expiry of the lock-in period, the Tenant shall pay a penalty equivalent "
            "to two months rent.",
        ),
        (
            "Rent Revision",
            "The monthly rent shall be Rs. 28,000/-. The rent may be increased by 8% every 12 "
            "months. The Landlord shall inform the Tenant of the proposed revision by written "
            "notice of 30 days before the revised rent becomes due.",
        ),
        (
            "Notice of Vacating",
            "The Tenant shall give 30 days written notice to the Landlord before vacating the "
            "premises. The Landlord shall also give 30 days notice before requiring the Tenant "
            "to vacate, save where eviction is ordered by the Rent Court.",
        ),
        (
            "Entry by Landlord",
            "The Landlord may enter the premises for inspection or repairs after giving 12 hours "
            "notice to the Tenant, during daytime hours.",
        ),
        (
            "Repairs and Maintenance",
            "The Tenant shall carry out routine repairs such as replacement of tap washers, "
            "drain cleaning, repairs to switches and sockets and replacement of glass panels. "
            "Structural repairs, whitewashing and internal wiring shall be attended to by the "
            "Landlord.",
        ),
        (
            "Essential Services",
            "The Landlord shall ensure uninterrupted supply of water and electricity and shall "
            "not disconnect or withhold these services for any reason.",
        ),
        (
            "Registration with Rent Authority",
            "The parties shall jointly submit this Agreement to the Rent Authority for "
            "registration in the manner prescribed under the Act, and the Landlord shall furnish "
            "one original signed and registered agreement to the Tenant.",
        ),
        (
            "Water and Electricity Charges",
            "Water charges shall be borne by the Landlord. Electricity consumption shall be paid "
            "by the Tenant as per the meter reading.",
        ),
        (
            "Governing Law",
            "This Agreement shall be governed by the Tamil Nadu Regulation of Rights and "
            "Responsibilities of Landlords and Tenants Act, 2017 and the rules made thereunder.",
        ),
    ),
    expected_min_violations=3,
)


TENANT_FRIENDLY = SampleLeaseSpec(
    sample_id="sample-tenant-friendly",
    title="Chennai - Thiruvanmiyur 3BHK, well-drafted agreement",
    tenant_persona="Family relocating with two children, long-term tenancy",
    property_description="3BHK apartment, 1,450 sq ft, Thiruvanmiyur, Chennai 600041",
    scenario=(
        "A family-lawyer-reviewed draft. Deposits, notice periods and repair obligations all "
        "track the Act. One minor item - the landlord keeps a spare key - is flagged as low risk."
    ),
    expected_risk_level=RiskLevel.LOW,
    monthly_rent_inr=48000,
    parties=(
        ("Landlord", "Dr. R. Meenakshi, No. 5, Kalakshetra Colony, Thiruvanmiyur, Chennai 600041"),
        ("Tenant", "Mr. V. Suresh Babu, No. 19, Adyar, Chennai 600020"),
        ("Premises", "Ground floor, No. 5, Kalakshetra Colony, Thiruvanmiyur, Chennai 600041"),
    ),
    preamble=(
        "This Rental Agreement is made on 10 December 2026 between the parties named above in "
        "respect of the residential premises described above.",
    ),
    clauses=(
        (
            "Period of Tenancy",
            "The tenancy shall be for a period of 24 months commencing on 1 January 2027, and "
            "may be renewed by mutual written agreement.",
        ),
        (
            "Security Deposit",
            "The Tenant shall pay a security deposit of Rs. 96,000/- equivalent to two months "
            "rent. The deposit is fully refundable, subject only to deduction of amounts actually "
            "due under this Agreement.",
        ),
        (
            "Refund of Security Deposit",
            "The Landlord shall refund the security deposit within 21 days after the Tenant "
            "vacates the premises, together with an itemised statement of any deductions and the "
            "supporting bills.",
        ),
        (
            "Lock-in Period",
            "The lock-in period shall be 6 months from the commencement date. If the Tenant "
            "terminates during the lock-in period, the Tenant shall pay one months rent in lieu "
            "of notice, and the security deposit shall not be forfeited.",
        ),
        (
            "Rent Revision",
            "The monthly rent shall be Rs. 48,000/-. The rent may be revised once in 12 months by "
            "not more than 5%, after the Landlord gives 90 days written notice of the proposed "
            "revision.",
        ),
        (
            "Notice of Termination",
            "Either party may terminate this Agreement by giving 60 days written notice to the "
            "other. Where the Tenant vacates without full notice, the Landlord may recover rent "
            "for the unexpired notice period only.",
        ),
        (
            "Entry with Notice",
            "The Landlord or the property manager may enter the premises only after giving 48 "
            "hours written notice, stating the reason for entry, and only between 7.00 A.M. and "
            "8.00 P.M., except in an emergency affecting life or property.",
        ),
        (
            "Keys",
            "The Tenant shall be given all keys to the premises. The Landlord shall retain one "
            "duplicate key solely for use in an emergency, and shall not use it to enter the "
            "premises otherwise than in accordance with the entry clause above.",
        ),
        (
            "Repairs and Maintenance",
            "The Landlord shall carry out structural repairs, whitewashing and painting of walls, "
            "replacement of plumbing lines and internal and external electrical wiring, in "
            "accordance with the Second Schedule to the Act. The Tenant shall carry out routine "
            "repairs such as tap washers, drain cleaning and replacement of switches.",
        ),
        (
            "Essential Services",
            "The Landlord shall not cut off or withhold water, electricity, lift or parking "
            "facilities. Any dispute shall be referred to the Rent Authority in accordance with "
            "the Act.",
        ),
        (
            "Registration",
            "The parties shall jointly inform the tenancy to the Rent Authority in the form "
            "prescribed in the First Schedule, and the Landlord shall give the Tenant one original "
            "signed and registered agreement within fifteen days of execution.",
        ),
        (
            "Utilities",
            "The Tenant shall pay electricity and water charges as per actual consumption, against "
            "copies of the relevant bills.",
        ),
        (
            "Governing Law",
            "This Agreement shall be governed by the Tamil Nadu Regulation of Rights and "
            "Responsibilities of Landlords and Tenants Act, 2017 and the rules framed thereunder.",
        ),
    ),
    expected_min_violations=1,
)


SAMPLE_SPECS: tuple[SampleLeaseSpec, ...] = (HIGH_RISK, ELEVATED_RISK, TENANT_FRIENDLY)


def get_spec(sample_id: str) -> SampleLeaseSpec | None:
    for spec in SAMPLE_SPECS:
        if spec.sample_id == sample_id:
            return spec
    return None
