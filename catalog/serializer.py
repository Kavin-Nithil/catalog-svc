from rest_framework import serializers
from .models import Category, Product, ProductReview
from django.utils.text import slugify


class CategorySerializer(serializers.ModelSerializer):
    """Category Serializer"""
    subcategories = serializers.SerializerMethodField()
    product_count = serializers.SerializerMethodField()

    class Meta:
        model = Category
        fields = [
            'id', 'name', 'slug', 'description', 'parent',
            'is_active', 'subcategories', 'product_count',
            'created_at', 'updated_at'
        ]
        read_only_fields = ['id', 'created_at', 'updated_at']

    def get_subcategories(self, obj):
        if obj.subcategories.exists():
            return CategorySerializer(
                obj.subcategories.filter(is_active=True),
                many=True
            ).data
        return []

    def get_product_count(self, obj):
        return Product.objects.filter(
            category=obj.name,
            is_active=True
        ).count()

    def create(self, validated_data):
        if 'slug' not in validated_data or not validated_data['slug']:
            validated_data['slug'] = slugify(validated_data['name'])
        return super().create(validated_data)


class ProductListSerializer(serializers.ModelSerializer):
    """Product List Serializer (lightweight for listing)"""
    is_in_stock = serializers.ReadOnlyField()
    is_low_stock = serializers.ReadOnlyField()

    class Meta:
        model = Product
        fields = [
            'product_id', 'sku', 'name', 'slug', 'category',
            'price', 'is_active', 'brand',
            'stock_quantity', 'is_in_stock', 'is_low_stock',
            'short_description', 'created_at'
        ]
        read_only_fields = ['product_id', 'created_at']


class ProductDetailSerializer(serializers.ModelSerializer):
    """Product Detail Serializer (full details)"""
    is_in_stock = serializers.ReadOnlyField()
    average_rating = serializers.SerializerMethodField()
    review_count = serializers.SerializerMethodField()

    class Meta:
        model = Product
        fields = [
            'product_id', 'sku', 'name', 'slug', 'category',
            'price', 'cost_price', 'is_active',
            'description', 'short_description', 'brand',
            'attributes',
            'stock_quantity',
            'is_in_stock', 'average_rating', 'review_count',
            'created_at', 'updated_at'
        ]
        read_only_fields = ['product_id', 'created_at', 'updated_at']

    def get_average_rating(self, obj):
        reviews = obj.reviews.filter(is_approved=True)
        if reviews.exists():
            from django.db.models import Avg
            avg = reviews.aggregate(Avg('rating'))['rating__avg']
            return round(avg, 2) if avg else 0
        return 0

    def get_review_count(self, obj):
        return obj.reviews.filter(is_approved=True).count()


class ProductCreateUpdateSerializer(serializers.ModelSerializer):
    """Product Create/Update Serializer"""

    class Meta:
        model = Product
        fields = [
            'product_id', 'sku', 'name', 'slug', 'category',
            'price', 'cost_price', 'is_active',
            'description', 'short_description', 'brand',
            'attributes', 'stock_quantity'
        ]

    def validate_price(self, value):
        if value <= 0:
            raise serializers.ValidationError("Price must be greater than 0")
        return value

    def validate_sku(self, value):
        # Check for unique SKU on update
        if self.instance:
            if Product.objects.filter(sku=value).exclude(
                    product_id=self.instance.product_id
            ).exists():
                raise serializers.ValidationError("SKU already exists")
        else:
            if Product.objects.filter(sku=value).exists():
                raise serializers.ValidationError("SKU already exists")
        return value

    def create(self, validated_data):
        if 'slug' not in validated_data or not validated_data['slug']:
            validated_data['slug'] = slugify(validated_data['name'])
        return super().create(validated_data)

    def update(self, instance, validated_data):
        if 'slug' in validated_data and not validated_data['slug']:
            validated_data['slug'] = slugify(validated_data.get('name', instance.name))
        return super().update(instance, validated_data)


class ProductSearchSerializer(serializers.Serializer):
    """Search Query Serializer"""
    q = serializers.CharField(required=False, allow_blank=True)
    category = serializers.ChoiceField(
        choices=['Electronics', 'Clothing', 'Books'],
        required=False
    )
    brand = serializers.CharField(required=False, allow_blank=True)
    min_price = serializers.DecimalField(
        max_digits=10, decimal_places=2, required=False
    )
    max_price = serializers.DecimalField(
        max_digits=10, decimal_places=2, required=False
    )
    is_active = serializers.BooleanField(required=False)
    is_featured = serializers.BooleanField(required=False)
    in_stock = serializers.BooleanField(required=False)
    tags = serializers.CharField(required=False, allow_blank=True)
    sort_by = serializers.ChoiceField(
        choices=[
            'price', '-price',
            'name', '-name',
            'created_at', '-created_at',
            'stock_quantity', '-stock_quantity'
        ],
        required=False,
        default='-created_at'
    )


class ProductReviewSerializer(serializers.ModelSerializer):
    """Product Review Serializer"""

    class Meta:
        model = ProductReview
        fields = [
            'id', 'product', 'customer_name', 'customer_email',
            'rating', 'title', 'comment', 'is_verified_purchase',
            'is_approved', 'created_at', 'updated_at'
        ]
        read_only_fields = ['id', 'is_verified_purchase', 'is_approved', 'created_at', 'updated_at']

    def validate_rating(self, value):
        if not 1 <= value <= 5:
            raise serializers.ValidationError("Rating must be between 1 and 5")
        return value


class BulkProductUpdateSerializer(serializers.Serializer):
    """Bulk Product Update Serializer"""
    product_ids = serializers.ListField(
        child=serializers.IntegerField(),
        min_length=1
    )
    updates = serializers.DictField(
        child=serializers.CharField(),
        help_text="Fields to update"
    )

    def validate_updates(self, value):
        allowed_fields = [
            'is_active', 'is_featured', 'price', 'stock_quantity',
            'is_available', 'category', 'brand'
        ]
        for key in value.keys():
            if key not in allowed_fields:
                raise serializers.ValidationError(
                    f"Field '{key}' cannot be bulk updated"
                )
        return value