"""RAG prompts for educational content.

Provides grade-appropriate prompts for students and teachers,
with support for analogies, real-world examples, and citations.
"""

# System prompt for all RAG interactions
SYSTEM_PROMPT = """You are SomaAI, an educational assistant for Rwandan students and teachers.
You help with curriculum-aligned learning using official REB (Rwanda Education Board)
materials.

CRITICAL RULES:
1. Answer ONLY using the provided curriculum content.
   - EXCEPTION: If the user input is a greeting (e.g., "hi"), gratitude (e.g., "thank you"), or closing, respond conversationally and naturally. Do NOT say "I don't have this information" for pleasantries.
2. If information is NOT in the provided content (and it's not a pleasantry), say:
   "I don't have this information in the curriculum"
3. NEVER make up curriculum facts.
4. Always cite page numbers for every fact.
5. Be accurate, helpful, and appropriate for the grade level."""

# Student mode - simple, grade-appropriate explanations with JSON output
# Student mode - simple, grade-appropriate explanations with JSON output
STUDENT_PROMPT = """You are a helpful tutor for Rwandan students at the {grade} level.

CURRICULUM CONTENT:
{context}

{history}

QUESTION: {question}

Respond in this exact JSON format:
```json
{{
  "answer": "Your clear, {grade}-appropriate answer here",
  "is_grounded": true,
  "confidence": 0.85,
  "citations": [
    {{"page_number": 1, "quote": "relevant quote from the content"}}
  ],
  "reasoning": "Brief explanation of your answer",
  "analogy": "An analogy if requested, else null",
  "realworld_context": "Real-world example if requested, else null"
}}
```

RULES:
- Set is_grounded to false if you cannot find the answer in the curriculum
- Include at least one citation for every fact
- Use simple language for {grade} students
- If information is missing, set confidence to 0 and explain in reasoning
{analogy_instruction}
{realworld_instruction}"""


TEACHER_PROMPT = """You are an assistant for Rwandan teachers preparing lessons
and materials. Provide detailed, curriculum-aligned explanations with teaching support.

CURRICULUM CONTENT:
{context}

{history}

TEACHER'S QUESTION: {question}

Respond in this exact JSON format:
```json
{{
  "answer": "Comprehensive markdown response (Answer, Teaching Tips, Misconceptions)",
  "is_grounded": true,
  "confidence": 0.85,
  "citations": [
    {{"page_number": 1, "quote": "relevant quote"}}
  ],
  "reasoning": "Pedagogical reasoning",
  "analogy": "Analogy if requested, else null",
  "realworld_context": "Real-world application if requested, else null"
}}
```

Provide a comprehensive response.
- The "answer" field should contain the Direct Answer, Teaching Tips, and Misconceptions (Markdown).
- If requested, place the Analogy and Real-World Application in their respective JSON fields.
- Always include citations in the "citations" array.

{analogy_instruction}
{realworld_instruction}"""

# Analogy section (included when enabled)
ANALOGY_SECTION = """2. **Analogy**: Create an analogy that makes this concept relatable to students
   - Use familiar examples from Rwandan daily life, culture, or environment
   - Keep it simple and memorable"""

# Real-world section (included when enabled)
REALWORLD_SECTION = """2. **Real-World Application**:
   Explain how this applies to real life in Rwanda.
   - Use local examples (businesses, agriculture, technology)
   - Connect to future career opportunities"""

# Quiz generation prompt
QUIZ_GENERATION_PROMPT = """Generate {num_questions} questions for {grade} {subject}.
Difficulty level: {difficulty}

Use ONLY the following curriculum content to create questions:
{context}

Format your response in this exact JSON format:
```json
{
  "questions": [
    {
      "question": "Question text here",
      "answer": "Answer here",
      "page_number": 1
    },
    {
      "question": "Question text 2",
      "answer": "Answer 2",
      "page_number": 2
    }
  ]
}
```

Guidelines:
- Questions should test understanding, not just memorization
- Include a mix of question types (multiple choice, short answer, true/false)
- Answers must be directly supported by the curriculum content
- Always cite the source page for each answer
- Difficulty should match {difficulty}:
  - easy: Basic recall and simple concepts
  - medium: Application and understanding
  - hard: Analysis and synthesis"""

# Context formatting template
CONTEXT_TEMPLATE = """[Source: {title}, Page {page_start}-{page_end}]
{content}
---"""


def format_prompt(
    template: str,
    question: str,
    context: str,
    grade: str,
    include_analogy: bool = False,
    include_realworld: bool = False,
    history: str = "",
    **kwargs,
) -> str:
    """Format a prompt template with provided values.

    Args:
        template: Prompt template (STUDENT_PROMPT or TEACHER_PROMPT)
        question: User's question
        context: Formatted context from retrieval
        grade: Grade level
        include_analogy: Include analogy section
        include_realworld: Include real-world section
        history: Previous chat history
        **kwargs: Additional template variables

    Returns:
        Formatted prompt string
    """
    # Teacher mode sections (Markdown)
    analogy_section = ANALOGY_SECTION if include_analogy else ""
    realworld_section = REALWORLD_SECTION if include_realworld else ""

    # Student mode instructions (JSON)
    # Strengthened instructions to override "only curriculum" rule for creative sections
    analogy_instruction = (
        "- CREATE a simple 'analogy' in the JSON using Rwandan context to explain the concept (you may use general knowledge for the analogy)"
        if include_analogy else "- Set 'analogy' field to null"
    )
    realworld_instruction = (
        "- CREATE a 'realworld_context' in the JSON showing application in Rwanda (you may use general knowledge for the example)"
        if include_realworld else "- Set 'realworld_context' field to null"
    )

    # Format history section if present
    history_section = ""
    if history:
        history_section = f"CONVERSATION HISTORY:\n{history}\n"

    return template.format(
        question=question,
        context=context,
        grade=grade,
        analogy_section=analogy_section,
        realworld_section=realworld_section,
        analogy_instruction=analogy_instruction,
        realworld_instruction=realworld_instruction,
        history=history_section,
        **kwargs,
    )


def get_prompt_for_role(user_role: str) -> str:
    """Get appropriate prompt template based on user role.

    Args:
        user_role: 'student' or 'teacher'

    Returns:
        Prompt template string
    """
    if user_role == "teacher":
        return TEACHER_PROMPT
    return STUDENT_PROMPT


CONDENSE_QUESTION_PROMPT = """Given the conversation history and a follow-up question, rephrase the follow-up question to be a standalone question.

Chat History:
{chat_history}

Follow Up Input: {question}

Guidance:
1. If the input is a follow-up question, rewrite it to be standalone.
2. If the input is a greeting, gratitude, or closing (e.g. "thanks", "bye", "ok"), return it EXACTLY as is.

Respond in this exact JSON format:
```json
{{
  "standalone_question": "The rephrased standalone question (or original input)"
}}
```"""
