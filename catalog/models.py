from django.db import models
from django.core.validators import MinValueValidator, MaxValueValidator
from decimal import Decimal
import uuid
    
    
class Category(models.Model):
    """Product Category Model"""
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    name = models.CharField(max_length=100, unique=True)
    slug = models.SlugField(max_length=100, unique=True)
    description = models.TextField(blank=True, null=True)
    parent = models.ForeignKey(
        'self',
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name='subcategories'
    )
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'categories'
        ordering = ['name']
        verbose_name_plural = 'Categories'
        indexes = [
            models.Index(fields=['slug']),
            models.Index(fields=['is_active']),
            models.Index(fields=['name']),
        ]

    def __str__(self):
        return self.name
    
    
class Product(models.Model):
    """
    Product Model - Matches eci_products.csv structure

    Fields from CSV:
    - product_id: Unique product identifier (1-120)
    - sku: Stock Keeping Unit (SKU0001-SKU0120)
    - name: Product name (Prod1-Prod120)
    - category: Product category (Electronics, Clothing, Books)
    - price: Product price in decimal
    - is_active: Whether product is active/available
    """

    # Category choices based on CSV data
    CATEGORY_CHOICES = [
        ('Electronics', 'Electronics'),
        ('Clothing', 'Clothing'),
        ('Books', 'Books'),
    ]

    # Core fields from CSV
    product_id = models.IntegerField(
        primary_key=True,
        help_text="Unique product identifier from CSV"
    )
    sku = models.CharField(
        max_length=50,
        unique=True,
        db_index=True,
        help_text="Stock Keeping Unit (e.g., SKU0001)"
    )
    name = models.CharField(
        max_length=200,
        db_index=True,
        help_text="Product name (e.g., Prod1)"
    )
    category = models.CharField(
        max_length=50,
        choices=CATEGORY_CHOICES,
        db_index=True,
        help_text="Product category: Electronics, Clothing, or Books"
    )
    price = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        validators=[MinValueValidator(Decimal('0.01'))],
        help_text="Product selling price"
    )
    is_active = models.BooleanField(
        default=True,
        db_index=True,
        help_text="Whether the product is currently active/available"
    )

    # Extended fields for enhanced functionality
    slug = models.SlugField(
        max_length=200,
        unique=True,
        blank=True,
        null=True,
        help_text="URL-friendly product identifier"
    )
    description = models.TextField(
        blank=True,
        null=True,
        help_text="Detailed product description"
    )
    short_description = models.CharField(
        max_length=500,
        blank=True,
        null=True,
        help_text="Brief product description for listings"
    )

    # Pricing fields
    cost_price = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        validators=[MinValueValidator(Decimal('0.00'))],
        null=True,
        blank=True,
        help_text="Product cost price (for margin calculation)"
    )
    compare_at_price = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        validators=[MinValueValidator(Decimal('0.00'))],
        null=True,
        blank=True,
        help_text="Original price (for showing discounts)"
    )

    # Product classification
    brand = models.CharField(
        max_length=100,
        blank=True,
        null=True,
        db_index=True,
        help_text="Product brand/manufacturer"
    )
    model_number = models.CharField(
        max_length=100,
        blank=True,
        null=True,
        help_text="Model/part number"
    )

    # Inventory management
    stock_quantity = models.IntegerField(
        default=0,
        validators=[MinValueValidator(0)],
        help_text="Current stock quantity"
    )

    attributes = models.JSONField(
        default=dict,
        blank=True,
        null=True,
        help_text="Custom product attributes (color, size, specifications)"
    )
    #
    # # Product flags
    # is_featured = models.BooleanField(
    #     default=False,
    #     db_index=True,
    #     help_text="Featured product (shown prominently)"
    # )
    # is_available = models.BooleanField(
    #     default=True,
    #     help_text="Product availability status"
    # )
    # is_bestseller = models.BooleanField(
    #     default=False,
    #     help_text="Bestseller flag"
    # )
    # is_new = models.BooleanField(
    #     default=False,
    #     help_text="New arrival flag"
    # )

    # Timestamps
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'products'
        ordering = ['-created_at']
        verbose_name = 'Product'
        verbose_name_plural = 'Products'
        indexes = [
            models.Index(fields=['sku'], name='idx_product_sku'),
            models.Index(fields=['category', 'is_active'], name='idx_category_active'),
            # models.Index(fields=['is_active', 'is_featured'], name='idx_active_featured'),
            models.Index(fields=['price'], name='idx_product_price'),
            models.Index(fields=['-created_at'], name='idx_created_at'),
            models.Index(fields=['brand'], name='idx_product_brand'),
            models.Index(fields=['name'], name='idx_product_name'),
        ]

    def __str__(self):
        return f"{self.sku} - {self.name}"

    def save(self, *args, **kwargs):
        """Auto-generate slug if not provided"""
        if not self.slug:
            from django.utils.text import slugify
            base_slug = slugify(self.name)
            slug = base_slug
            counter = 1
            while Product.objects.filter(slug=slug).exclude(
                    product_id=self.product_id
            ).exists():
                slug = f"{base_slug}-{counter}"
                counter += 1
            self.slug = slug
        super().save(*args, **kwargs)

    @property
    def is_in_stock(self):
        """Check if product is in stock"""
        return self.stock_quantity > 0

    @property
    def profit_margin(self):
        """Calculate profit margin if cost_price is set"""
        if self.cost_price and self.cost_price > 0:
            margin = ((self.price - self.cost_price) / self.price) * 100
            return round(margin, 2)
        return None

    @property
    def discount_percentage(self):
        """Calculate discount percentage if compare_at_price is set"""
        if self.compare_at_price and self.compare_at_price > self.price:
            discount = ((self.compare_at_price - self.price) / self.compare_at_price) * 100
            return round(discount, 2)
        return None
    
    
class ProductReview(models.Model):
    """Product Review and Rating Model"""

    id = models.BigAutoField(primary_key=True)
    product = models.ForeignKey(
        Product,
        on_delete=models.CASCADE,
        related_name='reviews',
        help_text="Related product"
    )

    # Customer information
    customer_name = models.CharField(
        max_length=200,
        help_text="Customer name"
    )
    customer_email = models.EmailField(
        help_text="Customer email"
    )

    # Review content
    rating = models.IntegerField(
        validators=[MinValueValidator(1), MaxValueValidator(5)],
        help_text="Rating from 1 to 5 stars"
    )
    title = models.CharField(
        max_length=200,
        help_text="Review title/headline"
    )
    comment = models.TextField(
        help_text="Review comment/description"
    )

    # Review metadata
    is_verified_purchase = models.BooleanField(
        default=False,
        help_text="Whether this is from a verified purchase"
    )
    is_approved = models.BooleanField(
        default=False,
        db_index=True,
        help_text="Whether the review is approved for display"
    )
    helpful_count = models.IntegerField(
        default=0,
        help_text="Number of users who found this helpful"
    )

    # Timestamps
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'product_reviews'
        ordering = ['-created_at']
        verbose_name = 'Product Review'
        verbose_name_plural = 'Product Reviews'
        indexes = [
            models.Index(fields=['product', '-created_at'], name='idx_review_product'),
            models.Index(fields=['is_approved'], name='idx_review_approved'),
            models.Index(fields=['rating'], name='idx_review_rating'),
        ]

    def __str__(self):
        return f"Review by {self.customer_name} for {self.product.name} ({self.rating}★)"
    
    
class ProductImage(models.Model):
    """Additional Product Images Model"""

    id = models.BigAutoField(primary_key=True)
    product = models.ForeignKey(
        Product,
        on_delete=models.CASCADE,
        related_name='product_images',
        help_text="Related product"
    )
    image_url = models.URLField(
        max_length=500,
        help_text="Image URL"
    )
    alt_text = models.CharField(
        max_length=200,
        blank=True,
        null=True,
        help_text="Alternative text for image"
    )
    position = models.IntegerField(
        default=0,
        help_text="Display order"
    )
    is_primary = models.BooleanField(
        default=False,
        help_text="Primary product image"
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'product_images'
        ordering = ['position', 'created_at']
        verbose_name = 'Product Image'
        verbose_name_plural = 'Product Images'
        indexes = [
            models.Index(fields=['product', 'position'], name='idx_image_product'),
        ]

    def __str__(self):
        return f"Image for {self.product.name} (Position: {self.position})"