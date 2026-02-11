"""Mock curriculum data for RAG testing."""

from typing import Any

MOCK_CHUNKS: list[dict[str, Any]] = [
    {
        "doc_id": "reb_bio_s2_001",
        "doc_title": "REB Biology S2 - Cell Biology",
        "page_start": 12,
        "page_end": 12,
        "grade": "S2",
        "subject": "science",
        "content": (
            "Photosynthesis is the process by which green plants and some other "
            "organisms use sunlight to synthesize nutrients from carbon dioxide and "
            "water. Photosynthesis in plants generally involves the green pigment "
            "chlorophyll and generates oxygen as a by-product. The chemical equation "
            "is: 6CO₂ + 6H₂O + light energy → C₆H₁₂O₆ + 6O₂"
        ),
    },
    {
        "doc_id": "reb_bio_s2_001",
        "doc_title": "REB Biology S2 - Cell Biology",
        "page_start": 15,
        "page_end": 15,
        "grade": "S2",
        "subject": "science",
        "content": (
            "Cell respiration is the process by which organisms combine oxygen with "
            "foodstuff molecules, diverting the chemical energy in these substances "
            "into life-sustaining activities and discarding carbon dioxide and water "
            "as waste products. The process occurs in mitochondria and releases "
            "energy stored in glucose."
        ),
    },
    {
        "doc_id": "reb_math_s3_002",
        "doc_title": "REB Mathematics S3 - Algebra",
        "page_start": 23,
        "page_end": 23,
        "grade": "S3",
        "subject": "mathematics",
        "content": (
            "The Pythagorean theorem states that in a right-angled triangle, the "
            "square of the length of the hypotenuse (the side opposite the right "
            "angle) is equal to the sum of the squares of the lengths of the other "
            "two sides. This can be written as: a² + b² = c², where c represents "
            "the length of the hypotenuse."
        ),
    },
    {
        "doc_id": "reb_math_s3_002",
        "doc_title": "REB Mathematics S3 - Algebra",
        "page_start": 45,
        "page_end": 45,
        "grade": "S3",
        "subject": "mathematics",
        "content": (
            "Linear equations are algebraic equations in which each term is either a "
            "constant or the product of a constant and a single variable. A linear "
            "equation in one variable can be written in the form ax + b = 0, where a "
            "and b are constants and a ≠ 0. To solve for x, we isolate the variable: "
            "x = -b/a."
        ),
    },
    {
        "doc_id": "reb_hist_s1_003",
        "doc_title": "REB History S1 - Rwanda History",
        "page_start": 8,
        "page_end": 8,
        "grade": "S1",
        "subject": "history",
        "content": (
            "The Kingdom of Rwanda was a pre-colonial kingdom in East Africa that "
            "existed from the 15th century until 1961. The kingdom was ruled by the "
            "Mwami (king) and had a sophisticated administrative structure with "
            "different categories of chiefs responsible for land, cattle, and "
            "military affairs."
        ),
    },
    {
        "doc_id": "reb_phys_s4_004",
        "doc_title": "REB Physics S4 - Mechanics",
        "page_start": 34,
        "page_end": 34,
        "grade": "S4",
        "subject": "science",
        "content": (
            "Newton's First Law of Motion states that an object at rest stays at "
            "rest and an object in motion stays in motion with the same speed and in "
            "the same direction unless acted upon by an unbalanced force. This is "
            "also known as the law of inertia. Inertia is the tendency of an object "
            "to resist changes in its state of motion."
        ),
    },
    {
        "doc_id": "reb_chem_s3_005",
        "doc_title": "REB Chemistry S3 - Acids and Bases",
        "page_start": 19,
        "page_end": 19,
        "grade": "S3",
        "subject": "science",
        "content": (
            "Acids are substances that release hydrogen ions (H⁺) when dissolved in "
            "water. Common examples include hydrochloric acid (HCl), sulfuric acid "
            "(H₂SO₄), and citric acid found in lemons. The pH scale measures "
            "acidity, with values below 7 indicating acidic solutions. Strong acids "
            "completely dissociate in water."
        ),
    },
    {
        "doc_id": "reb_geo_s2_006",
        "doc_title": "REB Geography S2 - East Africa",
        "page_start": 56,
        "page_end": 56,
        "grade": "S2",
        "subject": "geography",
        "content": (
            "Rwanda is known as the 'Land of a Thousand Hills' due to its "
            "mountainous terrain. The country is located in the Great Rift Valley "
            "where the African Great Lakes region and East Africa converge. Rwanda's "
            "geography influences its climate, with variations in temperature and "
            "rainfall depending on altitude."
        ),
    },
    {
        "doc_id": "reb_bio_s1_007",
        "doc_title": "REB Biology S1 - Human Body",
        "page_start": 28,
        "page_end": 28,
        "grade": "S1",
        "subject": "science",
        "content": (
            "The human circulatory system consists of the heart, blood vessels, and "
            "blood. The heart pumps blood throughout the body, delivering oxygen and "
            "nutrients to cells and removing waste products. Blood travels through "
            "arteries away from the heart and returns through veins. The average "
            "adult has about 5 liters of blood."
        ),
    },
    {
        "doc_id": "reb_math_s2_008",
        "doc_title": "REB Mathematics S2 - Fractions",
        "page_start": 17,
        "page_end": 17,
        "grade": "S2",
        "subject": "mathematics",
        "content": (
            "A fraction represents a part of a whole or a division of quantities. It "
            "consists of a numerator (top number) and a denominator (bottom number). "
            "To add fractions, they must have a common denominator. For example: "
            "1/4 + 1/2 = 1/4 + 2/4 = 3/4. Fractions can be simplified by dividing "
            "both numerator and denominator by their greatest common divisor."
        ),
    },
    {
        "doc_id": "reb_math_s6_009",
        "doc_title": "REB Mathematics S6 - Calculus",
        "page_start": 30,
        "page_end": 30,
        "grade": "S6",
        "subject": "mathematics",
        "content": (
            "In calculus, the derivative measures the instantaneous rate of change "
            "of a function. For a function f(x), the derivative f'(x) represents "
            "the slope of the tangent line at any point x. The fundamental theorem "
            "of calculus links differentiation and integration, showing they are "
            "inverse processes."
        ),
    },
]
