#!/usr/bin/env python3
"""
ShopHive Brain Files

Business context for Ghost Cursor AI co-pilot.
Contains plain English rules - NO HTML tags or CSS selectors.
"""

# ============================================================================
# Brain Directory Structure
# ============================================================================

# brain/
# ├── platform.md                  # Global platform context (always loaded)
# └── pages/
#     ├── products.md              # Product-related business rules
#     ├── checkout.md              # Checkout flow rules
#     ├── settings.md              # User settings rules
#     └── assumptions.md           # Business calculation assumptions

# ============================================================================
# Platform Context (Always Loaded)
# ============================================================================

PLATFORM_BRAIN = """# ShopHive Platform Overview

ShopHive is a modern footwear store that sells premium sneakers and sportswear.
All currency is in USD ($). Free shipping applies automatically on orders over $75.
Standard return policy is 30 days from purchase date.

## Shipping Zones
- United States (all 50 states): Standard shipping
- Canada: International shipping available
- International: Contact customer support

## Payment Methods
- Credit/Debit Cards (Visa, Mastercard, American Express, Discover)
- PayPal
- Apple Pay
- Google Pay

## Order Statuses
- Processing: Order received, preparing for shipment
- Shipped: Order has been dispatched
- Out for Delivery: Courier is on the way
- Delivered: Order successfully delivered

## Return Policy
- 30 days from purchase date
- Items must be unworn and in original packaging
- Refunds processed to original payment method within 5-7 business days

## Customer Support
- Email: support@shophive.com
- Phone: 1-800-SHOPLINE (Mon-Fri 9am-6pm EST)
"""

# ============================================================================
# Products Page Context
# ============================================================================

PRODUCTS_BRAIN = """# Product Detail Page Context

This page displays individual product information including sizes, colors, and pricing.

## Sizing Information
- Shoes are sold in US Men's sizes 7 through 13
- Sizes run true to size for most customers
- If between sizes, consider sizing up for comfort

## Available Sizes
- Size 7: 12 units available
- Size 8: 18 units available
- Size 9: 15 units available
- Size 10: 20 units available (Most Popular!)
- Size 11: 8 units available
- Size 12: 5 units available
- Size 13: 3 units available

## Color Options
- Black: Classic, matches everything
- White: Clean, minimalist look
- Red: Bold, statement piece

## Product Care
- Leather upper: Clean with damp cloth, apply conditioner monthly
- Mesh upper: Machine washable in cold water
- Rubber outsole: Resistant to most surfaces, avoid sharp objects

## Stock Information
- Current inventory: 20 units
- Expected restock: 2024-02-15 if sold out
- Backorder available: Yes (4-6 week delivery)

## Pricing
- Regular price: $129.99
- Sale price: Available seasonally
- Student discount: 10% with verification
"""

# ============================================================================
# Checkout Page Context
# ============================================================================

CHECKOUT_BRAIN = """# Checkout Page Context

This page collects shipping information and payment details to complete an order.

## Shipping Address Requirements
- Valid street address (no P.O. boxes for express shipping)
- City, State, and 5-digit ZIP code
- Phone number for carrier notifications

## US State Abbreviations
- AL, AK, AZ, AR, CA, CO, CT, DE, FL, GA, HI, ID, IL, IN, IA, KS, KY, LA, ME, MD, MA, MI, MN, MS, MO, MT, NE, NV, NH, NJ, NM, NY, NC, ND, OH, OK, OR, PA, RI, SC, SD, TN, TX, UT, VT, VA, WA, WV, WI, WY

## Shipping Options
- Standard (5-7 business days): Free on orders $75+
- Expedited (3-4 business days): $9.99
- Express (1-2 business days): $19.99

## Payment Security
- All transactions are SSL encrypted
- Card information never touches our servers
- PCI-DSS compliant payment processing

## Order Confirmation
- Email confirmation sent immediately
- Order can be tracked via email link
- Estimated delivery date provided at checkout

## Gift Options
- Gift wrapping available ($9.99)
- Gift message included
- Receipt not included in gift packages
"""

# ============================================================================
# Settings Page Context
# ============================================================================

SETTINGS_BRAIN = """# Settings Page Context

This page manages user preferences and notification settings.

## Appearance
- Light mode: Default theme with light background
- Dark mode: Dark background for low-light environments
- Theme preference saved across devices

## Notification Preferences
- Email: Receive order updates, promotions, and newsletters
- SMS: Shipping notifications and delivery alerts (standard rates apply)
- Push: Browser notifications for order updates and deals

## Account Security
- Password: Minimum 8 characters with numbers and letters
- Two-factor authentication: Recommended for account protection
- Session management: View and sign out from all devices

## Saved Addresses
- Up to 5 addresses can be saved
- Set default address for faster checkout
- Address labels: Home, Work, Other

## Privacy Settings
- Data retention: 7 years for tax compliance
- GDPR rights: Request data deletion or export
- Cookie preferences: Manage tracking preferences
"""

# ============================================================================
# Assumptions Page (Business Logic)
# ============================================================================

ASSUMPTIONS_BRAIN = """# ShopHive Business Assumptions

## Profit Margins
- Average gross margin: 35%
- Premium products: 40-45% margin
- Clearance items: 20-25% margin

## Shipping Costs
- Standard shipping cost to customer: Free over $75
- Internal shipping cost: $4.50 per order
- Expedited shipping: $9.99 charged to customer
- Express shipping: $19.99 charged to customer

## Promotional Calculations
- Standard promo codes: 10%, 20%, 25%, 30% off
- Free shipping threshold: $75 minimum order
- Buy one, get one: 50% off second item

## Inventory Management
- Reorder point: When stock reaches 15% of monthly sales
- Lead time: 14 days from supplier
- Safety stock: 10% of average monthly demand

## Tax Rates
- Sales tax: Varies by state (4-9%)
- Tax calculated at checkout based on shipping address
- Tax not charged on gift cards

## Returns
- Return rate: 8% of orders
- Restocking fee: None for standard returns
- Refund timeline: 5-7 business days after return received
"""

# ============================================================================
# Main Entry Point
# ============================================================================

def get_platform_brain() -> str:
    """Returns the platform brain context"""
    return PLATFORM_BRAIN

def get_page_brain(page_name: str) -> str:
    """Returns the brain context for a specific page"""
    brains = {
        "products": PRODUCTS_BRAIN,
        "product_detail": PRODUCTS_BRAIN,
        "checkout": CHECKOUT_BRAIN,
        "settings": SETTINGS_BRAIN,
        "assumptions": ASSUMPTIONS_BRAIN,
    }
    return brains.get(page_name, PRODUCTS_BRAIN)

def get_all_brain() -> str:
    """Returns all brain contexts concatenated"""
    return "\n\n".join([
        PLATFORM_BRAIN,
        PRODUCTS_BRAIN,
        CHECKOUT_BRAIN,
        SETTINGS_BRAIN,
        ASSUMPTIONS_BRAIN,
    ])