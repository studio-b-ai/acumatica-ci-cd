# Heritage Fabrics — Answer Connect Call Script

## Greeting

> "Thank you for calling Heritage Fabrics, this is [your name]. How can I help you today?"

---

## Stock Check

**Customer says:** "Do you have [item] in stock?" / "How much [fabric] do you have?" / "Check availability on [item]"

**Steps:**
1. Ask: "Sure, do you have the item number, or should I search by name?"
2. Open **cs-order-entry** → search by item number or description
3. Review availability by warehouse
4. Respond:
   - **In stock:** "We have [quantity] [UOM] available at our [warehouse] location. Would you like me to have someone from our sales team follow up with you?"
   - **Low stock:** "We have [quantity] [UOM] remaining. That's running low — would you like me to have our team reach out before it sells out?"
   - **Out of stock:** "That item is currently out of stock. I'll make a note of your interest — can I get your name and the best number to reach you? Our team will follow up when it's back in."
5. Log the call in cs-order-entry (caller, item, quantity asked, availability result, outcome)

---

## Price Check

**Customer says:** "What's the price on [item]?" / "How much is [fabric]?" / "Can I get a quote?"

**Steps:**
1. Ask: "Sure, do you have the item number?"
2. Open **cs-order-entry** → search by item number or description
3. Find the default price and UOM
4. Respond: "The current price on [item] is [price] per [UOM]."
5. If the customer asks about volume pricing or custom pricing:
   > "Volume and account-specific pricing is handled by our sales team. Let me get your info and have someone reach out to you."
   → Log as escalation
6. Log the call in cs-order-entry

---

## Account / General Info

**Customer says:** "What's my account number?" / "Can you update my address?" / "Do you carry [product type]?"

**Steps:**
1. Look up the customer in **HubSpot** by name, company, or phone number
2. For simple lookups (address, contact on file, account info): answer directly from HubSpot
3. For updates (address change, new contact, etc.):
   > "I'll make a note of that change and have our team update your account. Is there anything else I can help with?"
   → Log as Info Request with notes about the change needed
4. For general product questions you can't answer:
   > "Great question — let me have someone from our team get back to you on that. Can I confirm your callback number?"
   → Log as escalation

---

## Order Status / Shipping / Tracking

**Customer says:** "Where's my order?" / "When will my shipment arrive?" / "I need a tracking number"

**Response:**
> "I'd be happy to help with that. Let me get your information and have our team look into it for you. Can I get your name and the best number to reach you?"

**Steps:**
1. Get: customer name, company name, callback number
2. Ask: "Do you have an order number or PO reference?" (note it if they do)
3. Log as **Escalation** in cs-order-entry → auto-creates HubSpot ticket
4. Confirm: "Someone from our team will call you back within 2 hours."

---

## Returns / Claims / Complaints

**Customer says:** "I need to return..." / "There's a problem with my order" / "I received the wrong item" / "I'm not happy with..."

**Response:**
> "I'm sorry to hear that. Let me get your details so the right person can help you as quickly as possible."

**Steps:**
1. Get: customer name, company name, callback number
2. Ask: "Can you briefly describe the issue so I can pass it along?"
3. Note the issue description
4. Log as **Escalation** in cs-order-entry → auto-creates HubSpot ticket
5. Confirm: "I've flagged this with our team. Someone will call you back within 2 hours."

---

## Calls You Cannot Handle

If the caller asks about anything not covered above, or if you're unsure:

> "That's a great question. Let me connect you with someone who can help. Can I get your name and the best callback number?"

Log as **Escalation** with notes about what the caller asked.

---

## Ending the Call

After resolving or logging:

> "Is there anything else I can help you with today?"

If no:

> "Thanks for calling Heritage Fabrics. Have a great day!"

---

## Quick Reference

| Scenario | Tool | Action |
|----------|------|--------|
| Stock check | cs-order-entry | Search item → report availability → log call |
| Price check | cs-order-entry | Search item → quote price/UOM → log call |
| Account info | HubSpot | Look up contact/company → answer or log |
| Order status | cs-order-entry | Log as escalation → auto-ticket |
| Shipping/tracking | cs-order-entry | Log as escalation → auto-ticket |
| Returns/claims | cs-order-entry | Log as escalation → auto-ticket |
| Complaints | cs-order-entry | Log as escalation → auto-ticket |
| Don't know | cs-order-entry | Log as escalation → auto-ticket |

## Callback Timeframes

- Stock/price follow-ups: "by end of business today"
- Order status / shipping: "within 2 hours"
- Returns / complaints: "within 2 hours"
- General: "within one business day"

## Tools Access

- **cs-order-entry:** `cs-order-entry-production.up.railway.app`
- **HubSpot:** `app.hubspot.com` (use your assigned login)
