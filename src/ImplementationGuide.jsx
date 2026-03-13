import { useState } from "react";

const ImplementationGuide = () => {
  const [activeAgent, setActiveAgent] = useState("scout");
  const [copiedPrompt, setCopiedPrompt] = useState(null);

  const copyToClipboard = (text, id) => {
    navigator.clipboard.writeText(text).catch(() => {});
    setCopiedPrompt(id);
    setTimeout(() => setCopiedPrompt(null), 2000);
  };

  const agents = {
    scout: {
      name: "Scout",
      role: "Market Research Agent",
      icon: "🔍",
      color: "#E8B931",
      overview:
        "Scout runs weekly to identify profitable niches and generate product briefs. It analyzes what's trending on Etsy, Gumroad, and Pinterest, then outputs structured briefs for the Creator agent.",
      systemPrompt: `You are Scout, a market research AI agent for a digital product business. Your job is to identify profitable niches for digital products (templates, planners, ebooks, printables, spreadsheets).

RESEARCH PROCESS:

1. Analyze the trending category or keyword I give you
1. Identify 3-5 specific product opportunities within that niche
1. For each opportunity, provide a structured product brief

OUTPUT FORMAT (JSON):
{
  "niche": "Category name",
  "market_signals": ["Signal 1", "Signal 2"],
  "opportunities": [
    {
      "product_name": "Specific product title",
      "format": "Canva template / Notion template / PDF / Spreadsheet",
      "target_audience": "Specific demographic",
      "price_point": "$X",
      "competitor_gap": "What existing products miss",
      "search_keywords": ["kw1", "kw2", "kw3"],
      "difficulty": "easy / medium / hard",
      "estimated_demand": "high / medium / low",
      "product_brief": "2-3 sentence description of exactly what to create"
    }
  ]
}

GUIDELINES:

- Focus on evergreen niches with consistent demand
- Prioritize products that can be created by AI (text-heavy, template-based)
- Price between $5-$25 for individual products
- Look for gaps: poor design, missing features, underserved sub-niches
- Favor products with high perceived value but low creation complexity`,
      userPromptExample: `Research the niche: "ADHD productivity tools"

Consider these trending signals:

- Pinterest searches for "ADHD planner" up 240% YoY
- Top Etsy results have 10,000+ sales
- Most existing products are generic — not tailored to ADHD-specific needs

Find 3-5 specific product opportunities with full briefs.`,
      automationFlow: [
        { step: 1, tool: "Make.com Scheduler", action: "Triggers every Monday at 9 AM", detail: "Weekly cron trigger starts the research cycle" },
        { step: 2, tool: "Google Trends Module", action: "Pulls trending searches in your niche categories", detail: "Monitors 5-10 seed categories you define (productivity, wellness, finance, education, etc.)" },
        { step: 3, tool: "Claude API (HTTP Module)", action: "Sends trending data + Scout system prompt", detail: "POST to api.anthropic.com/v1/messages with the system prompt above and trending data as user message" },
        { step: 4, tool: "JSON Parser", action: "Parses Scout's structured output", detail: "Extracts the opportunities array from Claude's response" },
        { step: 5, tool: "Google Sheets", action: "Logs all opportunities to your Product Pipeline sheet", detail: "Adds each opportunity as a row with status 'Pending Review'" },
        { step: 6, tool: "Filter Module", action: "Auto-approves high-demand, easy-difficulty products", detail: "Products matching criteria go directly to Creator agent" },
      ],
      makeComSetup: `MAKE.COM SCENARIO: "Weekly Scout Research"

TRIGGER: Schedule → Every Monday, 9:00 AM

MODULE 1: HTTP → Make a Request
URL: https://api.anthropic.com/v1/messages
Method: POST
Headers:
  x-api-key: {{your_claude_api_key}}
  anthropic-version: 2023-06-01
  Content-Type: application/json
Body:
{
  "model": "claude-sonnet-4-20250514",
  "max_tokens": 4000,
  "system": "{{scout_system_prompt}}",
  "messages": [
    {
      "role": "user",
      "content": "Research these trending niches this week: {{google_trends_data}}. Find 3-5 product opportunities per niche."
    }
  ]
}

MODULE 2: JSON → Parse
Input: {{HTTP.body.content[0].text}}

MODULE 3: Iterator → Loop through opportunities array

MODULE 4: Google Sheets → Add a Row
Spreadsheet: "Product Pipeline"
Sheet: "Opportunities"
Values:
  A: {{item.product_name}}
  B: {{item.format}}
  C: {{item.target_audience}}
  D: {{item.price_point}}
  E: {{item.search_keywords}}
  F: {{item.product_brief}}
  G: "Pending"
  H: {{now}}`,
      tips: [
        "Start with 5-10 seed niches you're interested in — productivity, wellness, small business, parenting, students, etc.",
        "Use Google Trends free tier to validate demand before creating anything",
        "The best niches combine high search volume with low-quality existing products",
        "Run Scout manually the first few times to calibrate before automating",
        "Add a 'winner' column to your spreadsheet and track which briefs lead to actual sales — this trains your instincts over time",
      ],
    },
    creator: {
      name: "Creator",
      role: "Product Generation Agent",
      icon: "🎨",
      color: "#4ECDC4",
      overview:
        "Creator takes product briefs from Scout and generates the actual digital products. It works with Claude for content and structure, then uses Canva API or Google Docs for visual formatting.",
      systemPrompt: `You are Creator, a digital product generation AI agent. You receive product briefs and produce complete, ready-to-sell digital products.

YOUR CAPABILITIES:

- Write full ebook/guide content (5,000-15,000 words)
- Design template structures and layouts
- Create spreadsheet formulas and frameworks
- Write planner/worksheet content with clear sections
- Generate Notion template structures

PRODUCT CREATION RULES:

1. Every product must feel premium — not AI-generated slop
1. Use specific, actionable content (not generic filler)
1. Include clear visual hierarchy instructions for formatting
1. Add "bonus" elements that increase perceived value (checklists, quick-reference cards, etc.)
1. Write in a warm, expert tone — like a knowledgeable friend

OUTPUT FORMAT:
{
  "product_title": "Final product title",
  "tagline": "One-line value proposition",
  "format": "ebook / template / spreadsheet / planner",
  "pages_or_sections": [
    {
      "section_title": "Section Name",
      "content": "Full text content for this section",
      "design_notes": "Layout instructions for formatting agent",
      "elements": ["checklist", "table", "callout box", "etc"]
    }
  ],
  "bonus_materials": [
    {
      "title": "Bonus item name",
      "type": "checklist / cheat sheet / template",
      "content": "Full content"
    }
  ],
  "cover_text": {
    "title": "Cover title",
    "subtitle": "Cover subtitle",
    "author": "Your Brand Name"
  }
}

QUALITY STANDARDS:

- No placeholder text — everything must be real, usable content
- Specific examples and actionable steps, not vague advice
- Each section should stand alone as valuable
- Include page/section count appropriate to price point ($5 = 10-15 pages, $15 = 30-50 pages, $25 = 50+ pages)`,
      userPromptExample: `Create this product from the following brief:

PRODUCT BRIEF:

- Name: "The ADHD-Friendly Daily Planner System"
- Format: PDF planner (printable)
- Target: College students with ADHD
- Price: $12
- Gap: Existing planners are too rigid and overwhelming for ADHD brains

Requirements:

- Flexible structure (not hour-by-hour)
- Visual priority system (not just to-do lists)
- Built-in dopamine rewards and progress tracking
- Brain dump sections for capturing scattered thoughts
- Weekly review that's actually quick (5 min max)

Generate the complete product with all sections and content.`,
      automationFlow: [
        { step: 1, tool: "Google Sheets Trigger", action: "Watches for new approved briefs", detail: "When a row in Product Pipeline changes status to 'Approved', trigger Creator" },
        { step: 2, tool: "Claude API (HTTP Module)", action: "Sends brief + Creator system prompt", detail: "Generates complete product content in structured JSON" },
        { step: 3, tool: "Router Module", action: "Routes by product format", detail: "PDF → Google Docs path, Template → Canva path, Spreadsheet → Google Sheets path" },
        { step: 4, tool: "Google Docs API", action: "Creates formatted document from content", detail: "Applies headings, lists, tables, and styling based on design_notes" },
        { step: 5, tool: "Google Drive", action: "Exports as PDF", detail: "Converts the formatted doc to a polished PDF" },
        { step: 6, tool: "Google Sheets", action: "Updates pipeline status to 'Created'", detail: "Logs the product file URL and moves to QA queue" },
      ],
      makeComSetup: `MAKE.COM SCENARIO: "Creator - Product Generation"

TRIGGER: Google Sheets → Watch Rows
Spreadsheet: "Product Pipeline"
Sheet: "Opportunities"
Filter: Column G (Status) = "Approved"

MODULE 1: HTTP → Make a Request (Claude API)
URL: https://api.anthropic.com/v1/messages
Method: POST
Headers: (same as Scout)
Body:
{
  "model": "claude-sonnet-4-20250514",
  "max_tokens": 8000,
  "system": "{{creator_system_prompt}}",
  "messages": [
    {
      "role": "user",
      "content": "Create this product:\\n\\nTitle: {{row.product_name}}\\nFormat: {{row.format}}\\nAudience: {{row.target_audience}}\\nPrice: {{row.price_point}}\\nBrief: {{row.product_brief}}"
    }
  ]
}

MODULE 2: JSON → Parse Claude's response

MODULE 3: Router
  Route 1: IF format = "PDF" or "ebook" → Google Docs path
  Route 2: IF format = "spreadsheet" → Google Sheets path
  Route 3: IF format = "Canva template" → Canva API path

ROUTE 1 (PDF/Ebook):
MODULE 4a: Google Docs → Create a Document
  Title: {{product_title}}
  Content: {{formatted sections with headings}}

MODULE 5a: Google Drive → Export File
  File: {{new_doc_id}}
  Format: PDF

ROUTE 2 (Spreadsheet):
MODULE 4b: Google Sheets → Create a Spreadsheet
  (Build from Creator's structured output)

MODULE 6: Google Sheets → Update Row
  Pipeline Status: "Created"
  File URL: {{exported_file_url}}`,
      tips: [
        "For ebooks, have Creator generate content in chunks — introduction, then chapter by chapter. This avoids token limits and produces better content.",
        "Always include 1-2 'bonus' items. A $12 product with 3 bonuses feels like a $30 value.",
        "Templates should be 80% done for the user — not blank. Pre-filled examples dramatically increase perceived value.",
        "Test your first 3 products manually before automating. This helps you calibrate quality expectations.",
        "Keep a 'brand voice' document that Creator references. Consistency across products builds trust and repeat buyers.",
      ],
    },
    editor: {
      name: "Editor",
      role: "Quality & Brand Agent",
      icon: "✨",
      color: "#FF6B6B",
      overview:
        "Editor is your quality gate. Every product passes through Editor before listing. It checks for errors, brand consistency, and overall polish. It can send products back to Creator for revision.",
      systemPrompt: `You are Editor, a quality assurance AI agent for a digital product business. You review every product before it goes live.

REVIEW CHECKLIST:

1. CONTENT QUALITY
   - No grammatical or spelling errors
   - All content is specific and actionable (no filler)
   - Appropriate depth for the price point
   - No placeholder or template text left in
1. BRAND CONSISTENCY
   - Matches our brand voice: warm, expert, encouraging
   - No corporate jargon or stiff language
   - Consistent formatting throughout
   - Professional but approachable tone
1. VALUE ASSESSMENT
   - Would someone pay the listed price for this?
   - Does it solve the stated problem effectively?
   - Are there enough "wow" moments (tips, frameworks, bonuses)?
   - Does it feel premium, not AI-generated?
1. TECHNICAL CHECK
   - All sections are complete
   - Tables/checklists are properly formatted
   - No broken references or missing content
   - Page count appropriate for price

OUTPUT FORMAT:
{
  "verdict": "APPROVED" | "REVISION_NEEDED" | "REJECTED",
  "quality_score": 1-10,
  "issues": [
    {
      "severity": "critical" | "minor",
      "location": "Section name or page",
      "issue": "Description of problem",
      "suggested_fix": "How to fix it"
    }
  ],
  "strengths": ["What's working well"],
  "revision_instructions": "If REVISION_NEEDED, specific instructions for Creator agent",
  "listing_notes": "If APPROVED, notes for the Merchant agent about key selling points"
}

STANDARDS:

- Score of 7+ = APPROVED
- Score of 4-6 = REVISION_NEEDED (send back with specific fixes)
- Score below 4 = REJECTED (brief was flawed, send back to Scout)
- Be honest but constructive — the goal is shipping great products, not perfection`,
      userPromptExample: `Review this product for quality and brand consistency:

PRODUCT: "The ADHD-Friendly Daily Planner System"
PRICE: $12
TARGET: College students with ADHD

[Full product content would be inserted here from Creator's output]

Check against our brand guidelines:

- Voice: Warm, encouraging, zero judgment
- Design: Clean, not cluttered (critical for ADHD audience)
- Value: Must justify $12 price point
- Specificity: Real techniques, not generic advice`,
      automationFlow: [
        { step: 1, tool: "Google Sheets Trigger", action: "Watches for 'Created' status products", detail: "When Creator finishes, Editor automatically picks up the product" },
        { step: 2, tool: "Google Drive", action: "Downloads the product file", detail: "Fetches the PDF/doc for review" },
        { step: 3, tool: "Claude API (HTTP Module)", action: "Sends product content + Editor system prompt", detail: "Claude reviews against quality checklist" },
        { step: 4, tool: "Router Module", action: "Routes based on verdict", detail: "APPROVED → Merchant, REVISION_NEEDED → back to Creator, REJECTED → back to Scout" },
        { step: 5, tool: "Google Sheets", action: "Updates status and logs QA results", detail: "Records score, issues, and routing decision" },
        { step: 6, tool: "Email (optional)", action: "Notifies you of rejections", detail: "You only need to intervene when products are rejected — everything else is automated" },
      ],
      makeComSetup: `MAKE.COM SCENARIO: "Editor - Quality Gate"

TRIGGER: Google Sheets → Watch Rows
Filter: Status = "Created"

MODULE 1: Google Drive → Download a File
  File ID: {{row.file_url}}

MODULE 2: Text Parser → Extract text from PDF
  (Or use the document content directly if stored as text)

MODULE 3: HTTP → Claude API
Body:
{
  "model": "claude-sonnet-4-20250514",
  "max_tokens": 3000,
  "system": "{{editor_system_prompt}}",
  "messages": [
    {
      "role": "user",
      "content": "Review this product:\\n\\nTitle: {{row.product_name}}\\nPrice: {{row.price_point}}\\nAudience: {{row.target_audience}}\\n\\nContent:\\n{{extracted_text}}"
    }
  ]
}

MODULE 4: JSON → Parse verdict

MODULE 5: Router
  Route 1: verdict = "APPROVED" → Update status to "QA Passed"
  Route 2: verdict = "REVISION_NEEDED" → Update status to "Revision Needed" + store revision instructions
  Route 3: verdict = "REJECTED" → Update status to "Rejected" + send email alert

MODULE 6: Google Sheets → Update Row with QA results`,
      tips: [
        "Editor catches about 30% of products on first pass — that's normal and good. It means your quality bar is working.",
        "After 20+ products, analyze what Editor flags most. Update Creator's system prompt to prevent recurring issues.",
        "For your first month, review Editor's verdicts yourself. Once you trust its judgment, let it run fully automated.",
        "The 'listing_notes' output is gold — it tells Merchant exactly what to emphasize in the product description.",
        "Consider having Editor also generate a 'product mockup description' that helps with thumbnail creation.",
      ],
    },
    merchant: {
      name: "Merchant",
      role: "Listing & SEO Agent",
      icon: "🏪",
      color: "#A78BFA",
      overview:
        "Merchant takes approved products and publishes them to your sales channels. It writes SEO-optimized titles, descriptions, and tags, then handles the actual listing process via marketplace APIs.",
      systemPrompt: `You are Merchant, a marketplace listing and SEO agent for a digital product business. You create optimized listings that rank well and convert browsers into buyers.

YOUR PLATFORMS:

- Etsy (primary - massive built-in audience)
- Gumroad (secondary - higher margins, direct sales)

LISTING CREATION RULES:

TITLES (Critical for SEO):

- Front-load the main keyword
- Include the product type (planner, template, ebook, etc.)
- Add a benefit or audience modifier
- Stay under 140 characters for Etsy
- Example: "ADHD Daily Planner for College Students | Printable ADHD-Friendly Productivity System | Digital Download"

DESCRIPTIONS:

- Open with the #1 pain point your product solves
- List 5-7 specific features as bullet points
- Include social proof language ("Join 500+ students who…")
- Add FAQ section for common questions
- End with clear call to action
- Naturally include 8-12 relevant keywords

TAGS (Etsy allows 13 tags, max 20 chars each):

- Mix broad and specific keywords
- Include audience terms ("college student", "adhd")
- Include format terms ("printable", "digital download", "pdf")
- Include problem terms ("productivity", "time management")

OUTPUT FORMAT:
{
  "etsy_listing": {
    "title": "SEO-optimized title",
    "description": "Full listing description",
    "tags": ["tag1", "tag2", "... up to 13"],
    "category_suggestion": "Best Etsy category",
    "price": "$X.XX",
    "thumbnail_text": "Text to overlay on product mockup image"
  },
  "gumroad_listing": {
    "name": "Product name",
    "description": "Gumroad-optimized description (shorter, more direct)",
    "price": "$X.XX",
    "call_to_action": "Button text"
  },
  "seo_keywords": {
    "primary": "main keyword",
    "secondary": ["kw1", "kw2", "kw3"],
    "long_tail": ["long tail phrase 1", "long tail phrase 2"]
  }
}`,
      userPromptExample: `Create marketplace listings for this approved product:

PRODUCT: "The ADHD-Friendly Daily Planner System"
FORMAT: Printable PDF (8.5x11, also A4 version)
PRICE: $12
AUDIENCE: College students with ADHD
KEY SELLING POINTS (from Editor):

- Flexible time-blocking (not rigid hourly)
- Built-in dopamine reward system
- 5-minute weekly review
- Brain dump pages
- Includes 3 bonus checklists

Generate optimized listings for both Etsy and Gumroad.`,
      automationFlow: [
        { step: 1, tool: "Google Sheets Trigger", action: "Watches for 'QA Passed' status", detail: "Editor's approval triggers Merchant automatically" },
        { step: 2, tool: "Claude API", action: "Generates listing copy with Merchant prompt", detail: "Creates SEO-optimized titles, descriptions, and tags" },
        { step: 3, tool: "Canva API (optional)", action: "Generates product mockup thumbnails", detail: "Creates listing images using product cover + mockup template" },
        { step: 4, tool: "Etsy API", action: "Creates draft listing on Etsy", detail: "Uploads product file, images, and listing copy" },
        { step: 5, tool: "Gumroad API", action: "Creates product on Gumroad", detail: "Publishes with Gumroad-specific description" },
        { step: 6, tool: "Google Sheets", action: "Updates status to 'Listed' with URLs", detail: "Records both listing URLs and publication date" },
      ],
      makeComSetup: `MAKE.COM SCENARIO: "Merchant - Listing Publisher"

TRIGGER: Google Sheets → Watch Rows
Filter: Status = "QA Passed"

MODULE 1: HTTP → Claude API
  Generate listing copy using Merchant system prompt
  Include Editor's listing_notes in the user message

MODULE 2: JSON → Parse listing data

MODULE 3: Etsy API → Create Draft Listing
  (Etsy API requires OAuth — set up once)
  Title: {{etsy_listing.title}}
  Description: {{etsy_listing.description}}
  Tags: {{etsy_listing.tags}}
  Price: {{etsy_listing.price}}
  Digital: true

NOTE: You may prefer to use Etsy's CSV bulk upload
instead of API. Merchant can generate a CSV row that
you upload weekly in bulk.

MODULE 4: Gumroad API → Create Product
  URL: https://api.gumroad.com/v2/products
  Name: {{gumroad_listing.name}}
  Description: {{gumroad_listing.description}}
  Price: {{gumroad_listing.price}}

MODULE 5: Google Drive → Upload product file to listings

MODULE 6: Google Sheets → Update with listing URLs`,
      tips: [
        "Etsy SEO is the #1 growth lever. Spend time getting titles and tags right — they compound over months.",
        "Start with Gumroad if Etsy's API feels complex. Gumroad is simpler and you can always add Etsy later.",
        "Create a 'listing template' in Canva for product mockups. Merchant describes what text to put on it, and you (or a Canva automation) swaps it in.",
        "Price slightly higher than you think — $12 outsells $7 on Etsy because buyers associate price with quality for digital products.",
        "Use Merchant's long-tail keywords for your blog posts (Herald agent) — this creates an SEO flywheel.",
      ],
    },
    herald: {
      name: "Herald",
      role: "Marketing & Growth Agent",
      icon: "📣",
      color: "#F472B6",
      overview:
        "Herald drives traffic to your listings through content marketing. It creates Pinterest pins, social media posts, blog articles, and email sequences — all optimized for organic discovery.",
      systemPrompt: `You are Herald, a content marketing AI agent for a digital product business. You drive free organic traffic through strategic content creation.

CHANNEL STRATEGY:

1. PINTEREST (Primary - highest ROI for digital products)
   - Create 5-10 pins per product
   - Each pin targets a different keyword angle
   - Use benefit-driven headlines, not product names
1. BLOG/SEO (Secondary - compounds over time)
   - Write 1-2 articles per week
   - Target long-tail keywords from Merchant's research
   - Each article naturally links to relevant products
1. EMAIL (Retention - highest conversion rate)
   - Welcome sequence for new subscribers (5 emails)
   - Weekly newsletter with tips + product highlights
   - Launch emails for new products
1. SOCIAL MEDIA (Awareness - 1 platform only to start)
   - Choose: Instagram OR TikTok based on audience
   - 3-5 posts per week
   - Mix: tips (60%), product showcases (20%), behind-scenes (20%)

OUTPUT FORMATS:

For Pinterest:
{
  "pins": [
    {
      "headline": "Pin title (benefit-driven, 40-60 chars)",
      "description": "SEO description with keywords (up to 500 chars)",
      "board": "Board name",
      "link": "Product URL",
      "image_text": "Text to overlay on pin image",
      "keywords": ["pinterest", "search", "keywords"]
    }
  ]
}

For Blog Posts:
{
  "title": "SEO blog title",
  "meta_description": "155 chars",
  "target_keyword": "primary keyword",
  "outline": ["H2 sections"],
  "full_content": "Complete blog post (800-1500 words)",
  "internal_links": ["Products to link to"],
  "cta": "Call to action for email signup or product"
}

For Email Sequences:
{
  "sequence_name": "Welcome Series",
  "emails": [
    {
      "subject": "Email subject line",
      "preview_text": "Preview snippet",
      "body": "Full email content",
      "cta": "Button text and link",
      "send_delay": "Immediately / +1 day / +3 days"
    }
  ]
}`,
      userPromptExample: `Create a full marketing launch for this new product:

PRODUCT: "The ADHD-Friendly Daily Planner System"
ETSY URL: [etsy-link]
GUMROAD URL: [gumroad-link]
TARGET: College students with ADHD
KEYWORDS: adhd planner, adhd college, adhd productivity, adhd daily planner, adhd student planner

Generate:

1. 5 Pinterest pins with different keyword angles
1. 1 blog post targeting "adhd daily planner for college"
1. A product launch email for our existing subscribers`,
      automationFlow: [
        { step: 1, tool: "Google Sheets Trigger", action: "Watches for 'Listed' status products", detail: "New listing triggers marketing campaign creation" },
        { step: 2, tool: "Claude API", action: "Generates full marketing package", detail: "Pinterest pins + blog post + email using Herald prompt" },
        { step: 3, tool: "Tailwind API", action: "Schedules Pinterest pins", detail: "Spreads 5-10 pins across 2 weeks for optimal reach" },
        { step: 4, tool: "WordPress/Ghost API", action: "Publishes blog post", detail: "Or creates a draft for your review" },
        { step: 5, tool: "Mailchimp API", action: "Sends product launch email", detail: "To your subscriber list with personalized subject line" },
        { step: 6, tool: "Buffer API", action: "Schedules social media posts", detail: "3-5 posts across the week promoting the new product" },
      ],
      makeComSetup: `MAKE.COM SCENARIO: "Herald - Marketing Launch"

TRIGGER: Google Sheets → Watch Rows
Filter: Status = "Listed"

MODULE 1: HTTP → Claude API
  Generate full marketing package with Herald prompt
  Include product details, URLs, and keywords

MODULE 2: JSON → Parse marketing content

— PINTEREST PATH —
MODULE 3: Iterator → Loop through pins array

MODULE 4: Tailwind API → Schedule Pin
  (Tailwind has a Make.com integration)
  Board: {{pin.board}}
  Description: {{pin.description}}
  Link: {{pin.link}}
  Schedule: Smart Schedule (Tailwind picks optimal times)

— BLOG PATH —
MODULE 5: WordPress → Create Post (Draft)
  Title: {{blog.title}}
  Content: {{blog.full_content}}
  Status: Draft (review first month, then auto-publish)

— EMAIL PATH —
MODULE 6: Mailchimp → Create Campaign
  Subject: {{email.subject}}
  Content: {{email.body}}
  List: "All Subscribers"
  Schedule: Next business day, 10 AM

— SOCIAL PATH —
MODULE 7: Buffer → Create Post
  Text: {{social_post}}
  Channels: [your chosen platform]
  Schedule: Buffer's optimal time`,
      tips: [
        "Pinterest is your #1 traffic source. Period. Most digital product sellers get 60-80% of their traffic from Pinterest.",
        "Create a free 'lead magnet' version of your best product — a 1-page sample or mini template. Use it to build your email list.",
        "Blog posts take 2-3 months to rank in Google. Start early and be patient — they're your long-term growth engine.",
        "Email converts at 3-5x the rate of social media. Building your list is the most valuable thing Herald does.",
        "Don't spread across all social platforms. Pick ONE where your audience lives and do it well.",
      ],
    },
    concierge: {
      name: "Concierge",
      role: "Customer Support Agent",
      icon: "💬",
      color: "#34D399",
      overview:
        "Concierge handles all customer communication — from pre-sale questions to download issues to refund requests. It resolves 80-90% of issues automatically and escalates edge cases to you.",
      systemPrompt: `You are Concierge, a customer support AI agent for a digital product business. You handle customer inquiries with warmth, speed, and professionalism.

TONE: Friendly, helpful, empathetic. Like a really good barista who remembers your order.

RESPONSE CATEGORIES:

1. PRE-SALE QUESTIONS
   - Answer product questions using listing descriptions
   - Recommend products based on customer needs
   - Explain digital download process for first-time buyers
1. DOWNLOAD ISSUES (Most common)
   - Provide step-by-step download instructions
   - Offer alternative download links if needed
   - Troubleshoot common issues (file won't open, wrong format, etc.)
1. REFUND REQUESTS
   - Policy: Full refund within 30 days, no questions asked
   - Process refund immediately and thank them
   - Ask (optionally) what could be improved
1. FEEDBACK/REVIEWS
   - Thank positive feedback warmly
   - Address negative feedback constructively
   - Log all feedback for product improvement
1. ESCALATION (send to human)
   - Custom product requests
   - Technical issues you can't resolve
   - Angry customers who aren't satisfied with standard responses
   - Any legal or copyright concerns

OUTPUT FORMAT:
{
  "category": "pre-sale / download / refund / feedback / escalation",
  "response": "Your reply to the customer",
  "action_needed": "none / send_download_link / process_refund / escalate_to_human",
  "action_details": "Specific action parameters if needed",
  "feedback_log": "If feedback, what to log for product improvement",
  "escalation_reason": "If escalating, why"
}

RULES:

- Respond within the tone of our brand: warm, zero corporate speak
- Never say "I'm an AI" — just be helpful
- Always offer a solution, not just acknowledgment
- If uncertain, escalate rather than guess
- Keep responses concise — 2-4 sentences for simple issues`,
      userPromptExample: `Handle this customer email:

FROM: sarah.m@email.com
SUBJECT: Can't open the planner file

"Hi, I just bought the ADHD planner and I downloaded it but when I try to open it nothing happens. I'm on my iPad. Can you help? This is really frustrating because I need it for school tomorrow."

CONTEXT:

- Product: ADHD-Friendly Daily Planner System
- Format: PDF
- Purchase date: Today
- Platform: Etsy`,
      automationFlow: [
        { step: 1, tool: "Email Trigger (Gmail/Mailchimp)", action: "Incoming customer email detected", detail: "Watches your support email address for new messages" },
        { step: 2, tool: "Claude API", action: "Analyzes email + generates response", detail: "Classifies the issue and drafts a reply using Concierge prompt" },
        { step: 3, tool: "Router Module", action: "Routes based on action_needed", detail: "Auto-reply, process refund, send download link, or escalate" },
        { step: 4, tool: "Gmail", action: "Sends the response", detail: "Auto-replies from your support email address" },
        { step: 5, tool: "Google Sheets", action: "Logs the interaction", detail: "Records category, resolution, and any feedback for analysis" },
        { step: 6, tool: "Email to You (if escalation)", action: "Forwards edge cases to your personal email", detail: "You only handle the 10-20% that truly need a human" },
      ],
      makeComSetup: `MAKE.COM SCENARIO: "Concierge - Customer Support"

TRIGGER: Gmail → Watch Emails
Label/Filter: "Customer Support" or specific address

MODULE 1: HTTP → Claude API
Body:
{
  "model": "claude-sonnet-4-20250514",
  "max_tokens": 1500,
  "system": "{{concierge_system_prompt}}",
  "messages": [
    {
      "role": "user",
      "content": "Handle this customer email:\\n\\nFrom: {{email.from}}\\nSubject: {{email.subject}}\\nBody: {{email.body}}\\n\\nOur products: {{product_catalog_summary}}"
    }
  ]
}

MODULE 2: JSON → Parse response

MODULE 3: Router
  Route 1: action = "none" → Send reply
  Route 2: action = "send_download_link" → Fetch link + Send reply
  Route 3: action = "process_refund" → Etsy/Gumroad refund API + Send reply
  Route 4: action = "escalate_to_human" → Forward to your email

ROUTE 1 & 2:
MODULE 4: Gmail → Send Email
  To: {{original_sender}}
  Subject: Re: {{original_subject}}
  Body: {{concierge_response}}

ROUTE 3:
MODULE 4: Gumroad API → Refund
MODULE 5: Gmail → Send refund confirmation

ROUTE 4:
MODULE 4: Gmail → Forward
  To: your-personal@email.com
  Note: "ESCALATED: {{escalation_reason}}"

ALL ROUTES:
MODULE 6: Google Sheets → Log interaction
  Customer, Category, Resolution, Date`,
      tips: [
        "Set up a dedicated support email (support@yourbrand.com) rather than using your personal email.",
        "The #1 support issue for digital products is download problems. Create a standard 'how to download' PDF and have Concierge link to it.",
        "A 30-day no-questions refund policy actually reduces refund rates — it builds trust and removes buyer hesitation.",
        "Review Concierge's auto-replies for the first 2 weeks. Once you're confident, let it run fully automated.",
        "Use the feedback_log data monthly to identify product improvements. This is free market research.",
      ],
    },
  };

  const currentAgent = agents[activeAgent];

  const CodeBlock = ({ children, id }) => (
    <div style={{ position: "relative", background: "#13131A", border: "1px solid rgba(255,255,255,0.06)", borderRadius: 10, marginBottom: 16, overflow: "hidden" }}>
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", padding: "8px 16px", borderBottom: "1px solid rgba(255,255,255,0.06)", background: "rgba(255,255,255,0.02)" }}>
        <span style={{ fontFamily: "'Space Mono', monospace", fontSize: 10, color: "#5A5A70", letterSpacing: 1.5, textTransform: "uppercase" }}>Prompt</span>
        <button
          onClick={() => copyToClipboard(children, id)}
          style={{ background: copiedPrompt === id ? "#34D39920" : "rgba(255,255,255,0.05)", border: "1px solid rgba(255,255,255,0.1)", borderRadius: 6, padding: "4px 12px", color: copiedPrompt === id ? "#34D399" : "#8888A0", fontSize: 11, cursor: "pointer", fontFamily: "'Space Mono', monospace" }}
        >
          {copiedPrompt === id ? "✓ Copied" : "Copy"}
        </button>
      </div>
      <pre style={{ padding: 16, margin: 0, fontSize: 12, lineHeight: 1.7, color: "#A0A0B8", overflowX: "auto", whiteSpace: "pre-wrap", wordBreak: "break-word", fontFamily: "'Space Mono', monospace", maxHeight: 400 }}>{children}</pre>
    </div>
  );

  return (
    <div style={{ fontFamily: "'DM Sans', sans-serif", background: "#0A0A0F", color: "#E8E8ED", minHeight: "100vh" }}>
      <link href="https://fonts.googleapis.com/css2?family=DM+Sans:wght@400;500;700&family=Space+Mono:wght@400;700&display=swap" rel="stylesheet" />

      {/* Header */}
      <div style={{ background: "linear-gradient(135deg, #0A0A0F 0%, #1A1A2E 50%, #16213E 100%)", borderBottom: "1px solid rgba(255,255,255,0.06)", padding: "40px 24px 32px" }}>
        <div style={{ maxWidth: 960, margin: "0 auto" }}>
          <div style={{ fontFamily: "'Space Mono', monospace", fontSize: 11, letterSpacing: 4, color: "#A78BFA", textTransform: "uppercase", marginBottom: 10 }}>Implementation Guide</div>
          <h1 style={{ fontSize: 30, fontWeight: 700, margin: "0 0 10px", background: "linear-gradient(135deg, #E8E8ED 0%, #A78BFA 100%)", WebkitBackgroundClip: "text", WebkitTextFillColor: "transparent" }}>
            Agent Prompts & Automation Flows
          </h1>
          <p style={{ fontSize: 15, color: "#7A7A90", margin: 0, maxWidth: 600, lineHeight: 1.6 }}>
            Copy-paste ready prompts for each AI agent, plus step-by-step Make.com automation setup.
          </p>
        </div>
      </div>

      {/* Agent Tabs */}
      <div style={{ position: "sticky", top: 0, zIndex: 10, background: "rgba(10,10,15,0.95)", backdropFilter: "blur(12px)", borderBottom: "1px solid rgba(255,255,255,0.04)", padding: "0 24px", overflowX: "auto" }}>
        <div style={{ maxWidth: 960, margin: "0 auto", display: "flex", gap: 0 }}>
          {Object.entries(agents).map(([key, agent]) => (
            <button
              key={key}
              onClick={() => setActiveAgent(key)}
              style={{
                background: "none", border: "none", padding: "14px 16px", cursor: "pointer",
                borderBottom: activeAgent === key ? `2px solid ${agent.color}` : "2px solid transparent",
                transition: "all 0.2s", display: "flex", alignItems: "center", gap: 8, whiteSpace: "nowrap",
              }}
            >
              <span style={{ fontSize: 16 }}>{agent.icon}</span>
              <span style={{ fontFamily: "'Space Mono', monospace", fontSize: 11, letterSpacing: 1, color: activeAgent === key ? agent.color : "#5A5A70", textTransform: "uppercase" }}>{agent.name}</span>
            </button>
          ))}
        </div>
      </div>

      {/* Content */}
      <div style={{ maxWidth: 960, margin: "0 auto", padding: "36px 24px" }}>
        {/* Agent Header */}
        <div style={{ display: "flex", alignItems: "center", gap: 16, marginBottom: 24 }}>
          <div style={{ width: 56, height: 56, borderRadius: 14, background: currentAgent.color + "18", display: "flex", alignItems: "center", justifyContent: "center", fontSize: 30 }}>{currentAgent.icon}</div>
          <div>
            <h2 style={{ margin: 0, fontSize: 24, fontWeight: 700 }}>
              <span style={{ color: currentAgent.color }}>{currentAgent.name}</span>
              <span style={{ color: "#5A5A70", fontWeight: 400, fontSize: 16, marginLeft: 12 }}>{currentAgent.role}</span>
            </h2>
            <p style={{ margin: "4px 0 0", fontSize: 14, color: "#7A7A90", lineHeight: 1.6 }}>{currentAgent.overview}</p>
          </div>
        </div>

        {/* System Prompt */}
        <div style={{ marginBottom: 36 }}>
          <h3 style={{ fontFamily: "'Space Mono', monospace", fontSize: 12, letterSpacing: 2, color: currentAgent.color, textTransform: "uppercase", marginBottom: 12 }}>System Prompt (Copy This)</h3>
          <CodeBlock id={`${activeAgent}-system`}>{currentAgent.systemPrompt}</CodeBlock>
        </div>

        {/* Example User Message */}
        <div style={{ marginBottom: 36 }}>
          <h3 style={{ fontFamily: "'Space Mono', monospace", fontSize: 12, letterSpacing: 2, color: currentAgent.color, textTransform: "uppercase", marginBottom: 12 }}>Example User Message</h3>
          <CodeBlock id={`${activeAgent}-example`}>{currentAgent.userPromptExample}</CodeBlock>
        </div>

        {/* Automation Flow */}
        <div style={{ marginBottom: 36 }}>
          <h3 style={{ fontFamily: "'Space Mono', monospace", fontSize: 12, letterSpacing: 2, color: currentAgent.color, textTransform: "uppercase", marginBottom: 16 }}>Make.com Automation Flow</h3>
          <div style={{ position: "relative", paddingLeft: 28 }}>
            <div style={{ position: "absolute", left: 11, top: 8, bottom: 8, width: 2, background: `linear-gradient(to bottom, ${currentAgent.color}, ${currentAgent.color}33)` }} />
            {currentAgent.automationFlow.map((step) => (
              <div key={step.step} style={{ position: "relative", marginBottom: 20, paddingLeft: 24 }}>
                <div style={{ position: "absolute", left: -17, top: 6, width: 12, height: 12, borderRadius: "50%", background: currentAgent.color, boxShadow: `0 0 10px ${currentAgent.color}44` }} />
                <div style={{ display: "flex", gap: 8, alignItems: "center", marginBottom: 4 }}>
                  <span style={{ fontFamily: "'Space Mono', monospace", fontSize: 10, color: currentAgent.color }}>{step.step}</span>
                  <span style={{ fontSize: 12, fontWeight: 700, color: "#E8E8ED" }}>{step.tool}</span>
                </div>
                <div style={{ fontSize: 14, fontWeight: 500, marginBottom: 2 }}>{step.action}</div>
                <div style={{ fontSize: 12, color: "#6B6B80", lineHeight: 1.5 }}>{step.detail}</div>
              </div>
            ))}
          </div>
        </div>

        {/* Make.com Setup Details */}
        <div style={{ marginBottom: 36 }}>
          <h3 style={{ fontFamily: "'Space Mono', monospace", fontSize: 12, letterSpacing: 2, color: currentAgent.color, textTransform: "uppercase", marginBottom: 12 }}>Make.com Scenario Setup</h3>
          <CodeBlock id={`${activeAgent}-make`}>{currentAgent.makeComSetup}</CodeBlock>
        </div>

        {/* Pro Tips */}
        <div style={{ marginBottom: 36 }}>
          <h3 style={{ fontFamily: "'Space Mono', monospace", fontSize: 12, letterSpacing: 2, color: currentAgent.color, textTransform: "uppercase", marginBottom: 16 }}>Pro Tips</h3>
          <div style={{ background: "rgba(255,255,255,0.02)", border: "1px solid rgba(255,255,255,0.06)", borderRadius: 12, overflow: "hidden" }}>
            {currentAgent.tips.map((tip, i) => (
              <div key={i} style={{ padding: "14px 20px", borderBottom: i < currentAgent.tips.length - 1 ? "1px solid rgba(255,255,255,0.04)" : "none", fontSize: 13, color: "#9A9AB0", lineHeight: 1.7, display: "flex", gap: 12 }}>
                <span style={{ color: currentAgent.color, fontWeight: 700, flexShrink: 0 }}>→</span>
                <span>{tip}</span>
              </div>
            ))}
          </div>
        </div>

        {/* Quick Start Checklist */}
        <div style={{ background: `${currentAgent.color}08`, border: `1px solid ${currentAgent.color}22`, borderRadius: 12, padding: 24 }}>
          <h3 style={{ fontFamily: "'Space Mono', monospace", fontSize: 12, letterSpacing: 2, color: currentAgent.color, textTransform: "uppercase", margin: "0 0 14px" }}>Quick Start for {currentAgent.name}</h3>
          <div style={{ fontSize: 13, color: "#9A9AB0", lineHeight: 2 }}>
            {activeAgent === "scout" && <>1. Copy the system prompt above → 2. Open Claude.ai and paste it as your first message → 3. Ask it to research a niche you&apos;re interested in → 4. Review the output and adjust the prompt if needed → 5. Once happy, set it up in Make.com with the scenario above</>}
            {activeAgent === "creator" && <>1. Copy the system prompt → 2. Test it in Claude.ai with one of Scout&apos;s product briefs → 3. Review the product output for quality and completeness → 4. Iterate on the prompt until products feel premium → 5. Connect to Make.com to auto-trigger from approved briefs</>}
            {activeAgent === "editor" && <>1. Copy the system prompt → 2. Feed it one of Creator&apos;s products manually → 3. Check if Editor&apos;s quality assessment matches your own judgment → 4. Adjust scoring thresholds if needed → 5. Wire it up in Make.com between Creator and Merchant</>}
            {activeAgent === "merchant" && <>1. Set up your Gumroad account (takes 5 min) → 2. Copy the system prompt → 3. Test with an approved product → 4. Review listing copy for SEO quality → 5. Publish your first listing manually, then automate</>}
            {activeAgent === "herald" && <>1. Set up Tailwind account for Pinterest → 2. Create 5-10 Pinterest boards for your niches → 3. Copy the system prompt and test with a live product → 4. Schedule your first batch of pins → 5. Set up the blog (free WordPress.com or Ghost) for SEO content</>}
            {activeAgent === "concierge" && <>1. Set up a support email address → 2. Copy the system prompt → 3. Test with sample customer emails → 4. Set up Gmail forwarding rules → 5. Monitor auto-replies for 2 weeks before going fully automated</>}
          </div>
        </div>
      </div>
    </div>
  );
};

export default ImplementationGuide;
