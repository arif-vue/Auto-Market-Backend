import json
import re
import logging
import base64
from typing import Dict, Any, List, Optional
from openai import OpenAI

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class AutoMarketAIService:
    
    def __init__(self, api_key: str = None):
        """
        Initialize OpenAI client.
        Args:
            api_key: Your OpenAI API key. If None, will use OPENAI_API_KEY environment variable
        """
        import os
        actual_key = api_key or os.getenv('OPENAI_API_KEY')
        
        if not actual_key:
            raise ValueError("OpenAI API key not found. Please set OPENAI_API_KEY environment variable.")
        
        try:
            # Try initializing with explicit parameters to avoid proxy issues
            self.client = OpenAI(
                api_key=actual_key,
                timeout=30.0,
                max_retries=2
            )
        except Exception as e:
            logger.error(f"Failed to initialize OpenAI client: {e}")
            # For now, create a mock client that returns default values
            self.client = None
        
        # Using GPT-4 Turbo for best results (you can also use "gpt-3.5-turbo" for lower cost)
        self.model = "gpt-4-turbo-preview"
        self.temperature = 0.2  # Lower temperature for more consistent, conservative pricing
        self.max_tokens = 2048

    def _sanitize_input(self, text: str) -> str:
        """Clean input to avoid triggering safety filters."""
        if not text:
            return text
        
        # Remove lowercase 's' after digits: "3s" -> "3"
        text = re.sub(r'\b(\d+)s\b', r'\1', text)
        
        return text
    
    def _validate_price_reasonableness(self, price: float, item_name: str, description: str, condition: str) -> Dict[str, Any]:
        """
        Validate if the price seems reasonable. If suspiciously high, ask AI to reconsider.
        This is a SAFETY NET, not a restriction - works for ANY product.
        Returns: {"is_reasonable": bool, "concern": str or None}
        """
        # Generic pattern-based checks (not category-specific)
        concerns = []
        
        item_lower = item_name.lower()
        desc_lower = description.lower() if description else ""
        combined_text = item_lower + " " + desc_lower
        
        # Check 1: Words suggesting budget/generic items
        budget_indicators = ['budget', 'cheap', 'generic', 'no-brand', 'unknown brand', 'basic', 
                            'ikea', 'walmart', 'target', 'dollar store', 'used textbook', 'thrift']
        has_budget_indicator = any(indicator in combined_text for indicator in budget_indicators)
        
        if has_budget_indicator and price > 500:
            concerns.append(f"Item appears to be budget/generic but priced at ${price}")
        
        # Check 2: Any year mentioned in past (suggests used/old item)
        year_match = re.search(r'\b(19\d{2}|20[0-1]\d|202[0-5])\b', combined_text)
        if year_match:
            year = int(year_match.group(1))
            current_year = 2025
            age = current_year - year
            
            # Old items (>5 years) priced very high need review
            if age > 5 and price > 1000:
                concerns.append(f"Item from {year} ({age} years old) priced at ${price} - may need age-based depreciation")
            
            # Very old items (>10 years) at high prices
            if age > 10 and price > 500:
                concerns.append(f"Very old item ({year}, {age} years) priced at ${price} - verify collectible value")
        
        # Check 3: Poor condition items at high prices
        poor_condition_words = ['fair', 'poor', 'worn', 'damaged', 'broken', 'defective', 'parts']
        if any(word in condition.lower() for word in poor_condition_words):
            # Expensive items in poor condition need scrutiny
            if price > 1000:
                concerns.append(f"{condition} condition item priced at ${price} - verify discount applied")
            # Even moderate prices in poor condition
            elif price > 300 and 'broken' in condition.lower():
                concerns.append(f"Broken/damaged item priced at ${price} - may be too high")
        
        # Check 4: Words suggesting heavy use/damage
        damage_words = ['cracked', 'broken', 'damaged', 'worn out', 'defective', 'not working', 'for parts']
        if any(word in combined_text for word in damage_words) and price > 200:
            concerns.append(f"Item with damage/defects priced at ${price} - verify condition adjustment")
        
        # If concerns exist, trigger AI reconsideration (not rejection!)
        if concerns:
            return {
                "is_reasonable": False,
                "concern": "; ".join(concerns)
            }
        
        return {"is_reasonable": True, "concern": None}
    
    def estimate_price(self, item_name: str, description: str, 
                      condition: str, defects: str = "", 
                      images: List[str] = None, 
                      pickup_address: str = "") -> Dict[str, Any]:
        
        # If OpenAI client is not available, use fallback pricing
        if self.client is None:
            logger.warning("OpenAI client not available, using fallback pricing")
            return self._fallback_price_estimation(item_name, description, condition)
        
        try:
            item_name = self._sanitize_input(item_name)
            description = self._sanitize_input(description)
            
            image_analysis_text = ""
            if images and len(images) > 0:
                image_analysis = self._analyze_images(images, item_name, description)
                if image_analysis:
                    image_analysis_text = f"\n\nVISUAL INSPECTION FROM IMAGES:\n{json.dumps(image_analysis, indent=2)}"
            
            prompt = f"""You are a professional used product valuation expert with comprehensive knowledge of RESALE MARKETS across ALL product categories.

PRODUCT TO EVALUATE:
Item Name: {item_name}
Full Description: {description}
Current Condition: {condition}
Known Issues/Defects: {defects if defects else "None reported"}
Seller Location: {pickup_address if pickup_address else "Location not specified"}{image_analysis_text}

YOUR TASK - REALISTIC USED MARKET PRICE ESTIMATION:

STEP 1: IDENTIFY THE PRODUCT
- What exact category, brand, model is this?
- Is it specific (e.g., "iPhone 13 Pro 256GB") or generic (e.g., "office chair")?
- What is the original retail price when new?
- What is the typical depreciation rate for this category?

STEP 2: RESEARCH ACTUAL RESALE MARKET (CRITICAL)
Think like a smart buyer shopping on:
- eBay SOLD listings (not current listings - only completed sales)
- Facebook Marketplace actual prices
- Craigslist typical asking prices
- Poshmark, Mercari, OfferUp for applicable items
- CarGurus, Autotrader for vehicles
- Specialized marketplaces for specific categories

⚠️ CRITICAL: Use SOLD prices, not wishful listing prices. Many items are listed high but sell for 30-50% less.

STEP 3: APPLY DEPRECIATION & CONDITION ADJUSTMENTS

For USED items, calculate depreciation:
- Electronics: Lose 20-40% value per year (phones/laptops depreciate fast)
- Furniture: Used furniture typically sells for 30-60% of retail
- Appliances: Lose 30-50% immediately when used
- Vehicles: Follow standard depreciation curves (20% first year, 15% after)
- Luxury goods: Brand matters - some hold value (Rolex), others don't
- Generic items: Often worth very little used (IKEA furniture, basic items)

Condition adjustments:
- "Like New" / "Excellent": 85-95% of typical used price
- "Good": 70-85% of typical used price  
- "Fair": 50-70% of typical used price
- "Poor": 30-50% of typical used price

For each defect mentioned, reduce price by 5-15% depending on severity.

STEP 4: REALITY CHECKS

Ask yourself:
1. "Would I personally pay this price for this used item?"
2. "Can I find similar items selling for this price on eBay/Facebook right now?"
3. "Is this a reasonable discount from the new retail price?"
4. "Does this account for the condition and defects mentioned?"

⚠️ RED FLAGS - Reduce price if:
- Generic/no-brand items (IKEA, basic furniture) - these have low resale value
- Old electronics (>3 years) - depreciate heavily
- Common items with high supply - check if market is flooded
- Defects mentioned - each defect matters
- Fair/Poor condition - should be 50% or less of "Like New" price

STEP 5: LOCATION ADJUSTMENT (Minor, ±10% maximum)
- High cost of living areas (SF, NYC, Dubai): +5-10%
- Average areas: No adjustment
- Low cost areas: -5-10%

FINAL VALIDATION CHECKLIST:
✓ Is this price what similar items ACTUALLY SOLD for (not listed)?
✓ Does it account for ALL defects and condition issues?
✓ Is it realistic for a USED item (not retail price)?
✓ Would a smart buyer pay this on Facebook Marketplace TODAY?

Return ONLY this JSON (no other text):
{{
    "estimated_price": 0.00,
    "currency": "USD",
    "confidence": "HIGH",
    "price_range_min": 0.00,
    "price_range_max": 0.00
}}

EXAMPLES OF REALISTIC PRICING:
- Used iPhone 13 Pro 256GB (Good): ~$550-650 (not $800+)
- IKEA LACK coffee table (used): ~$10-20 (not $50+)
- 2019 Honda Civic 45k miles (Good): ~$18,000-20,000 (not $25,000+)
- Used designer bag (Fair condition, defects): 40-60% of retail, not 70-80%
- Generic furniture (used): Often 20-40% of retail

Remember: People buy USED items to save money. Price must reflect actual market reality, not optimistic estimates.

Calculate price range as ±15% of estimated_price.
Confidence: HIGH = common item with market data, MEDIUM = some data, LOW = rare/unique item"""

            response = self.client.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "system", "content": "You are a professional product valuation expert. Always respond with valid JSON only."},
                    {"role": "user", "content": prompt}
                ],
                temperature=self.temperature,
                max_tokens=self.max_tokens,
                response_format={"type": "json_object"}  # Force JSON response
            )
            
            response_text = response.choices[0].message.content
            
            if not response_text:
                logger.error("Empty response from OpenAI")
                return self._retry_pricing(item_name, description, condition, defects, pickup_address, image_analysis_text)
            
            result = self._parse_json(response_text)
            
            if not result.get("estimated_price"):
                logger.error("AI did not return a price, retrying with simpler prompt")
                return self._retry_pricing(item_name, description, condition, defects, pickup_address, image_analysis_text)
            
            price = float(result.get("estimated_price", 0))
            
            if price <= 0:
                logger.error(f"AI returned invalid price: {price}")
                return self._retry_pricing(item_name, description, condition, defects, pickup_address, image_analysis_text)
            
            # Validate price reasonableness
            validation = self._validate_price_reasonableness(price, item_name, description, condition)
            if not validation["is_reasonable"]:
                logger.warning(f"Price validation concern: {validation['concern']} - Asking AI to reconsider")
                return self._reconsider_pricing(item_name, description, condition, defects, pickup_address, 
                                               image_analysis_text, price, validation["concern"])
            
            confidence = result.get("confidence", "MEDIUM").upper()
            price_range_min = result.get("price_range_min", round(price * 0.85, 2))
            price_range_max = result.get("price_range_max", round(price * 1.15, 2))
            
            logger.info(f"Successfully estimated price for '{item_name}': ${price} (Confidence: {confidence})")
            
            return {
                "estimated_price": round(price, 2),
                "currency": "USD",
                "confidence": confidence,
                "price_range_min": round(price_range_min, 2),
                "price_range_max": round(price_range_max, 2)
            }
            
        except Exception as e:
            logger.error(f"Error in estimate_price: {str(e)}")
            return self._retry_pricing(item_name, description, condition, defects, pickup_address, "")
    
    def _analyze_images(self, image_paths: List[str], item_name: str, description: str) -> Optional[Dict[str, Any]]:
        """
        Analyze product images using GPT-4 Vision.
        Note: Requires gpt-4-vision-preview or gpt-4-turbo (with vision) model
        """
        try:
            # Convert images to base64
            image_contents = []
            for img_path in image_paths[:4]:  # OpenAI recommends max 4 images for best performance
                try:
                    with open(img_path, "rb") as image_file:
                        base64_image = base64.b64encode(image_file.read()).decode('utf-8')
                        image_contents.append({
                            "type": "image_url",
                            "image_url": {
                                "url": f"data:image/jpeg;base64,{base64_image}",
                                "detail": "high"
                            }
                        })
                    logger.info(f"Loaded image: {img_path}")
                except Exception as e:
                    logger.warning(f"Failed to load {img_path}: {e}")
            
            if not image_contents:
                return None
            
            prompt_text = f"""Analyze these product images for pricing purposes.

Product: {item_name}
Description: {description}

Assess the condition, defects, authenticity, and overall quality. Return JSON:
{{
    "condition": "excellent/good/fair/poor",
    "defects": ["list any visible defects"],
    "authenticity": "genuine/questionable/unknown",
    "quality_notes": "brief assessment"
}}"""
            
            # Build message content with text and images
            message_content = [{"type": "text", "text": prompt_text}] + image_contents
            
            response = self.client.chat.completions.create(
                model="gpt-4-turbo",  # or "gpt-4-vision-preview"
                messages=[
                    {
                        "role": "user",
                        "content": message_content
                    }
                ],
                max_tokens=500,
                response_format={"type": "json_object"}
            )
            
            return self._parse_json(response.choices[0].message.content)
            
        except Exception as e:
            logger.error(f"Image analysis failed: {str(e)}")
            return None
    
    def _parse_json(self, text: str) -> Dict[str, Any]:
        if not text or len(text.strip()) == 0:
            logger.error("Empty response from AI")
            return {}
            
        text = text.strip()
        
        if text.startswith("```json"):
            text = text[7:]
        if text.startswith("```"):
            text = text[3:]
        if text.endswith("```"):
            text = text[:-3]
        text = text.strip()
        
        try:
            return json.loads(text)
        except json.JSONDecodeError as e:
            logger.warning(f"Failed to parse JSON directly: {e}")
            match = re.search(r"\{[^{}]*(?:\{[^{}]*\}[^{}]*)*\}", text, re.DOTALL)
            if match:
                try:
                    return json.loads(match.group())
                except:
                    logger.error(f"Failed to parse extracted JSON. Raw text: {text[:200]}")
            else:
                logger.error(f"No JSON found in response. Raw text: {text[:200]}")
            return {}
    
    def _reconsider_pricing(self, item_name: str, description: str, condition: str,
                           defects: str, location: str, image_analysis: str,
                           initial_price: float, concern: str) -> Dict[str, Any]:
        """
        Ask AI to reconsider pricing when initial estimate seems too high.
        """
        try:
            logger.info(f"Reconsidering price: Initial ${initial_price} flagged due to: {concern}")
            
            reconsider_prompt = f"""You previously estimated ${initial_price} for this item, but this seems TOO HIGH.

CONCERN: {concern}

PRODUCT DETAILS:
Item: {item_name}
Description: {description}
Condition: {condition}
Defects: {defects if defects else "None"}
Location: {location if location else "Not specified"}{image_analysis}

RECONSIDER WITH THESE GUIDELINES:

1. RESALE MARKET REALITY CHECK:
   - What do similar USED items ACTUALLY SELL for on eBay, Facebook Marketplace?
   - NOT listing prices - SOLD prices (typically 30-50% lower than listings)
   - Used items are cheaper than new - buyers expect significant discounts

2. DEPRECIATION FACTORS:
   - Electronics: 20-40% loss per year (phones/tablets depreciate FAST)
   - Furniture: Used furniture = 30-60% of retail (generic brands like IKEA even less)
   - Appliances: Immediately lose 30-50% when used
   - Generic/no-brand items: Very low resale value

3. CONDITION REALITY:
   - "Fair" = 50-70% of "Like New" price (not 80-90%)
   - "Poor" = 30-50% of "Like New" price
   - Each defect = -5% to -15% reduction
   - {condition} condition with defects should be HEAVILY discounted

4. COMPARABLE SALES:
   Think: "Would someone actually pay ${initial_price} for this USED item when they could buy similar for less?"
   
5. BE CONSERVATIVE:
   - If uncertain, estimate LOWER (buyers appreciate good deals)
   - Better to under-estimate than over-estimate
   - Used market is competitive - price to sell

Provide a MORE REALISTIC, CONSERVATIVE price based on actual resale market conditions.

Return ONLY this JSON:
{{
    "estimated_price": 0.00,
    "currency": "USD",
    "confidence": "MEDIUM",
    "price_range_min": 0.00,
    "price_range_max": 0.00,
    "reasoning": "brief explanation of the revised price"
}}"""

            response = self.client.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "system", "content": "You are a conservative product valuation expert. Focus on realistic RESALE prices, not optimistic estimates. Respond with valid JSON only."},
                    {"role": "user", "content": reconsider_prompt}
                ],
                temperature=0.1,  # Even lower temperature for conservative estimates
                max_tokens=800,
                response_format={"type": "json_object"}
            )
            
            response_text = response.choices[0].message.content
            
            if not response_text:
                logger.error("Empty response from AI during reconsideration")
                return self._retry_pricing(item_name, description, condition, defects, location, image_analysis)
            
            result = self._parse_json(response_text)
            
            if result.get("estimated_price") and float(result["estimated_price"]) > 0:
                new_price = round(float(result["estimated_price"]), 2)
                
                # If still too high, apply a conservative cap
                if new_price >= initial_price * 0.9:  # Not much change
                    logger.warning(f"AI still estimated high: ${new_price}. Applying conservative adjustment.")
                    new_price = round(initial_price * 0.65, 2)  # Apply 35% reduction
                
                logger.info(f"Reconsidered price: ${initial_price} -> ${new_price}")
                
                confidence = result.get("confidence", "MEDIUM").upper()
                price_range_min = result.get("price_range_min", round(new_price * 0.85, 2))
                price_range_max = result.get("price_range_max", round(new_price * 1.15, 2))
                
                return {
                    "estimated_price": new_price,
                    "currency": "USD",
                    "confidence": confidence,
                    "price_range_min": round(price_range_min, 2),
                    "price_range_max": round(price_range_max, 2)
                }
            
            logger.error("Reconsideration failed to produce valid price")
            return self._retry_pricing(item_name, description, condition, defects, location, image_analysis)
            
        except Exception as e:
            logger.error(f"Price reconsideration failed: {str(e)}")
            return self._retry_pricing(item_name, description, condition, defects, location, image_analysis)
    
    
    def _retry_pricing(self, item_name: str, description: str, condition: str, 
                      defects: str, location: str, image_analysis: str) -> Dict[str, Any]:
        try:
            logger.info("Retrying price estimation with alternative approach")
            
            safe_item_name = self._sanitize_input(item_name)
            safe_description = self._sanitize_input(description) if len(description) > 0 else "Used product"
            
            simple_prompt = f"""What is the current market resale price in USD for this item?

Product name: {safe_item_name}
Brief info: {safe_description[:100]}
Physical condition: {condition}
Location: {location if location else "USA"}

Provide realistic market value based on typical resale prices.

Return only JSON format:
{{"estimated_price": 0.00, "currency": "USD", "confidence": "MEDIUM", "price_range_min": 0.00, "price_range_max": 0.00}}"""

            response = self.client.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "system", "content": "You are a product pricing expert. Respond with valid JSON only."},
                    {"role": "user", "content": simple_prompt}
                ],
                temperature=self.temperature,
                max_tokens=500,
                response_format={"type": "json_object"}
            )
            
            response_text = response.choices[0].message.content
            
            if not response_text:
                logger.error("Empty response from AI in retry")
                return self._final_fallback_pricing(item_name, condition)
            
            logger.info(f"AI retry response (first 200 chars): {response_text[:200]}")
            result = self._parse_json(response_text)
            
            if result.get("estimated_price") and float(result["estimated_price"]) > 0:
                price = round(float(result["estimated_price"]), 2)
                confidence = result.get("confidence", "MEDIUM").upper()
                price_range_min = result.get("price_range_min", round(price * 0.85, 2))
                price_range_max = result.get("price_range_max", round(price * 1.15, 2))
                
                return {
                    "estimated_price": price,
                    "currency": "USD",
                    "confidence": confidence,
                    "price_range_min": round(price_range_min, 2),
                    "price_range_max": round(price_range_max, 2)
                }
            
            logger.error("Retry also failed to get valid price")
            return self._final_fallback_pricing(item_name, condition)
            
        except Exception as e:
            logger.error(f"Retry pricing failed: {str(e)}")
            return self._final_fallback_pricing(item_name, condition)
    
    def _final_fallback_pricing(self, item_name: str, condition: str) -> Dict[str, Any]:
        """Final fallback using AI-extracted category."""
        try:
            logger.info("Using final fallback pricing with AI-extracted category")
            
            category_prompt = f"""What type of product is this? Return just the generic product category in 1-2 words.

Product: {item_name}

Return only the category name, nothing else."""

            try:
                category_response = self.client.chat.completions.create(
                    model=self.model,
                    messages=[
                        {"role": "user", "content": category_prompt}
                    ],
                    temperature=0.3,
                    max_tokens=20
                )
                category = category_response.choices[0].message.content.strip().lower()
                category = re.sub(r'[^a-z\s]', '', category).strip()
                if not category or len(category) > 30:
                    category = "used product"
            except:
                category = "used product"
            
            logger.info(f"AI detected category: {category}")
            
            generic_prompt = f"""What is the typical used market price for a {category} in {condition} condition?

Provide a realistic resale value estimate in USD.

Return JSON:
{{"estimated_price": 0.00, "currency": "USD", "confidence": "LOW", "price_range_min": 0.00, "price_range_max": 0.00}}"""

            response = self.client.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "system", "content": "You are a pricing expert. Respond with valid JSON only."},
                    {"role": "user", "content": generic_prompt}
                ],
                temperature=self.temperature,
                max_tokens=500,
                response_format={"type": "json_object"}
            )
            
            response_text = response.choices[0].message.content
            
            if response_text:
                result = self._parse_json(response_text)
                if result.get("estimated_price") and float(result["estimated_price"]) > 0:
                    price = round(float(result["estimated_price"]), 2)
                    return {
                        "estimated_price": price,
                        "currency": "USD",
                        "confidence": "LOW",
                        "price_range_min": round(price * 0.85, 2),
                        "price_range_max": round(price * 1.15, 2)
                    }
            
            logger.error("All pricing attempts failed")
            return {
                "estimated_price": 0.00,
                "currency": "USD",
                "confidence": "LOW",
                "price_range_min": 0.00,
                "price_range_max": 0.00,
                "error": "Unable to estimate price - please provide more details"
            }
            
        except Exception as e:
            logger.error(f"Final fallback failed: {str(e)}")
            return {
                "estimated_price": 0.00,
                "currency": "USD",
                "confidence": "LOW",
                "price_range_min": 0.00,
                "price_range_max": 0.00,
                "error": "Pricing service temporarily unavailable"
            }

    def _fallback_price_estimation(self, item_name: str, description: str, condition: str) -> Dict[str, Any]:
        """
        Fallback pricing when OpenAI is not available
        Uses simple keyword-based pricing logic
        """
        logger.info(f"Using fallback pricing for: {item_name}")
        
        # Basic keyword-based pricing
        item_lower = item_name.lower()
        desc_lower = description.lower() if description else ""
        combined_text = item_lower + " " + desc_lower
        
        base_price = 100.0  # Default base price
        
        # Device type pricing
        if any(word in combined_text for word in ['iphone', 'phone']):
            base_price = 400.0
        elif any(word in combined_text for word in ['macbook', 'laptop']):
            base_price = 800.0
        elif any(word in combined_text for word in ['ipad', 'tablet']):
            base_price = 300.0
        elif any(word in combined_text for word in ['tv', 'television']):
            base_price = 500.0
        elif any(word in combined_text for word in ['watch', 'smartwatch']):
            base_price = 200.0
        elif any(word in combined_text for word in ['car', 'vehicle', 'auto']):
            base_price = 15000.0
        elif any(word in combined_text for word in ['camera']):
            base_price = 400.0
        
        # Condition adjustments
        condition_multiplier = {
            'NEW': 0.9,
            'LIKE_NEW': 0.8,
            'EXCELLENT': 0.7,
            'GOOD': 0.6,
            'FAIR': 0.4,
            'POOR': 0.2
        }
        
        multiplier = condition_multiplier.get(condition, 0.6)
        estimated_price = base_price * multiplier
        
        # Price range
        price_range_min = estimated_price * 0.8
        price_range_max = estimated_price * 1.2
        
        return {
            "estimated_price": round(estimated_price, 2),
            "currency": "USD",
            "confidence": "LOW",
            "price_range_min": round(price_range_min, 2),
            "price_range_max": round(price_range_max, 2),
            "fallback": True,
            "note": "Price estimated using fallback method (OpenAI unavailable)"
        }
