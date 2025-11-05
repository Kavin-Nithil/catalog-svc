from rest_framework import viewsets, status, filters
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticatedOrReadOnly, AllowAny
from django.db.models import Q, Avg, Count
from django.shortcuts import get_object_or_404
from .models import Category, Product, ProductReview
from .serializer import (
    CategorySerializer,
    ProductListSerializer,
    ProductDetailSerializer,
    ProductCreateUpdateSerializer,
    ProductSearchSerializer,
    ProductReviewSerializer,
    BulkProductUpdateSerializer
)
import logging

logger = logging.getLogger(__name__)


class CategoryViewSet(viewsets.ModelViewSet):
    """
    ViewSet for Category CRUD operations
    """
    queryset = Category.objects.all()
    serializer_class = CategorySerializer
    permission_classes = [IsAuthenticatedOrReadOnly]
    lookup_field = 'id'

    def get_queryset(self):
        queryset = Category.objects.all()

        is_active = self.request.query_params.get('is_active')
        if is_active is not None:
            queryset = queryset.filter(is_active=is_active.lower() == 'true')

        parent = self.request.query_params.get('parent')
        if parent:
            if parent.lower() == 'null':
                queryset = queryset.filter(parent__isnull=True)
            else:
                queryset = queryset.filter(parent_id=parent)

        return queryset

    @action(detail=True, methods=['get'])
    def products(self, request, id=None):
        """Get all products in a category"""
        category = self.get_object()
        products = Product.objects.filter(
            category=category.name,
            is_active=True
        )

        page = self.paginate_queryset(products)
        if page is not None:
            serializer = ProductListSerializer(page, many=True)
            return self.get_paginated_response(serializer.data)

        serializer = ProductListSerializer(products, many=True)
        return Response(serializer.data)


class ProductViewSet(viewsets.ModelViewSet):
    """
    ViewSet for Product CRUD operations
    """
    queryset = Product.objects.all()
    permission_classes = [IsAuthenticatedOrReadOnly]
    lookup_field = 'product_id'
    filter_backends = [filters.OrderingFilter]
    ordering_fields = ['price', 'name', 'created_at', 'stock_quantity']
    ordering = ['-created_at']

    def get_serializer_class(self):
        if self.action == 'list':
            return ProductListSerializer
        elif self.action in ['create', 'update', 'partial_update']:
            return ProductCreateUpdateSerializer
        return ProductDetailSerializer

    def get_queryset(self):
        queryset = Product.objects.all()

        # Filter by active status (default: show only active)
        is_active = self.request.query_params.get('is_active')
        if is_active is not None:
            queryset = queryset.filter(is_active=is_active.lower() == 'true')
        elif self.action == 'list':
            # By default, only show active products in list view
            queryset = queryset.filter(is_active=True)

        # Filter by category
        category = self.request.query_params.get('category')
        if category:
            queryset = queryset.filter(category=category)

        return queryset

    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        product = serializer.save()

        # Publish event to RabbitMQ
        self._publish_event('product.created', product)

        logger.info(f"Product created: {product.sku}")
        return Response(
            ProductDetailSerializer(product).data,
            status=status.HTTP_201_CREATED
        )

    def update(self, request, *args, **kwargs):
        partial = kwargs.pop('partial', False)
        instance = self.get_object()
        serializer = self.get_serializer(instance, data=request.data, partial=partial)
        serializer.is_valid(raise_exception=True)
        product = serializer.save()

        # Publish event to RabbitMQ
        self._publish_event('product.updated', product)

        logger.info(f"Product updated: {product.sku}")
        return Response(ProductDetailSerializer(product).data)

    def destroy(self, request, *args, **kwargs):
        instance = self.get_object()
        sku = instance.sku

        # Soft delete - set is_active to False
        instance.is_active = False
        instance.save()

        # Publish event to RabbitMQ
        self._publish_event('product.deleted', instance)

        logger.info(f"Product soft deleted: {sku}")
        return Response(
            {'message': f'Product {sku} deactivated successfully'},
            status=status.HTTP_204_NO_CONTENT
        )

    @action(detail=False, methods=['get'])
    def search(self, request):
        """
        Advanced product search endpoint
        Query params: q, category, brand, min_price, max_price,
                     is_featured, in_stock, tags, sort_by
        """
        search_serializer = ProductSearchSerializer(data=request.query_params)
        search_serializer.is_valid(raise_exception=True)
        params = search_serializer.validated_data

        queryset = Product.objects.filter(is_active=True)

        # Text search across name, SKU, description
        if 'q' in params and params['q']:
            search_term = params['q']
            queryset = queryset.filter(
                Q(name__icontains=search_term) |
                Q(sku__icontains=search_term) |
                Q(description__icontains=search_term) |
                Q(brand__icontains=search_term)
            )

        # Category filter
        if 'category' in params:
            queryset = queryset.filter(category=params['category'])

        # Brand filter
        if 'brand' in params and params['brand']:
            queryset = queryset.filter(brand__iexact=params['brand'])

        # Price range filter
        if 'min_price' in params:
            queryset = queryset.filter(price__gte=params['min_price'])
        if 'max_price' in params:
            queryset = queryset.filter(price__lte=params['max_price'])

        # Featured filter
        if 'is_featured' in params:
            queryset = queryset.filter(is_featured=params['is_featured'])

        # In stock filter
        if 'in_stock' in params and params['in_stock']:
            queryset = queryset.filter(stock_quantity__gt=0)

        # Tags filter
        if 'tags' in params and params['tags']:
            tags = [tag.strip() for tag in params['tags'].split(',')]
            queryset = queryset.filter(tags__overlap=tags)

        # Sorting
        sort_by = params.get('sort_by', '-created_at')
        queryset = queryset.order_by(sort_by)

        # Pagination
        page = self.paginate_queryset(queryset)
        if page is not None:
            serializer = ProductListSerializer(page, many=True)
            return self.get_paginated_response(serializer.data)

        serializer = ProductListSerializer(queryset, many=True)
        return Response(serializer.data)

    @action(detail=False, methods=['get'], url_path='by-sku/(?P<sku>[^/.]+)')
    def by_sku(self, request, sku=None):
        """Get product by SKU"""
        try:
            product = Product.objects.get(sku=sku)
            serializer = ProductDetailSerializer(product)
            return Response(serializer.data)
        except Product.DoesNotExist:
            return Response(
                {'error': f'Product with SKU {sku} not found'},
                status=status.HTTP_404_NOT_FOUND
            )

    @action(detail=False, methods=['get'])
    def featured(self, request):
        """Get featured products"""
        queryset = Product.objects.filter(is_featured=True, is_active=True)

        page = self.paginate_queryset(queryset)
        if page is not None:
            serializer = ProductListSerializer(page, many=True)
            return self.get_paginated_response(serializer.data)

        serializer = ProductListSerializer(queryset, many=True)
        return Response(serializer.data)

    @action(detail=False, methods=['get'])
    def by_category(self, request):
        """Get products grouped by category with counts"""
        categories = ['Electronics', 'Clothing', 'Books']
        result = {}

        for category in categories:
            count = Product.objects.filter(
                category=category,
                is_active=True
            ).count()
            result[category] = {
                'count': count,
                'category': category
            }

        return Response(result)

    @action(detail=False, methods=['get'])
    def low_stock(self, request):
        """Get products with low stock"""
        queryset = Product.objects.filter(
            is_active=True,
            stock_quantity__gt=0,
            stock_quantity__lte=models.F('low_stock_threshold')
        )

        page = self.paginate_queryset(queryset)
        if page is not None:
            serializer = ProductListSerializer(page, many=True)
            return self.get_paginated_response(serializer.data)

        serializer = ProductListSerializer(queryset, many=True)
        return Response(serializer.data)

    @action(detail=False, methods=['get'])
    def out_of_stock(self, request):
        """Get out of stock products"""
        queryset = Product.objects.filter(
            is_active=True,
            stock_quantity=0
        )

        page = self.paginate_queryset(queryset)
        if page is not None:
            serializer = ProductListSerializer(page, many=True)
            return self.get_paginated_response(serializer.data)

        serializer = ProductListSerializer(queryset, many=True)
        return Response(serializer.data)

    @action(detail=False, methods=['post'])
    def bulk_update(self, request):
        """Bulk update products"""
        serializer = BulkProductUpdateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        product_ids = serializer.validated_data['product_ids']
        updates = serializer.validated_data['updates']

        # Update products
        updated_count = Product.objects.filter(
            product_id__in=product_ids
        ).update(**updates)

        logger.info(f"Bulk updated {updated_count} products")

        return Response({
            'message': f'Successfully updated {updated_count} products',
            'updated_count': updated_count
        })

    @action(detail=True, methods=['patch'])
    def update_stock(self, request, product_id=None):
        """Update product stock quantity"""
        product = self.get_object()
        quantity = request.data.get('stock_quantity')

        if quantity is None:
            return Response(
                {'error': 'stock_quantity is required'},
                status=status.HTTP_400_BAD_REQUEST
            )

        try:
            quantity = int(quantity)
            if quantity < 0:
                raise ValueError("Stock quantity cannot be negative")
        except ValueError as e:
            return Response(
                {'error': str(e)},
                status=status.HTTP_400_BAD_REQUEST
            )

        product.stock_quantity = quantity
        product.save()

        logger.info(f"Updated stock for {product.sku}: {quantity}")

        return Response({
            'product_id': product.product_id,
            'sku': product.sku,
            'stock_quantity': product.stock_quantity,
            'is_in_stock': product.is_in_stock,
            'is_low_stock': product.is_low_stock
        })

    @action(detail=True, methods=['get'])
    def reviews(self, request, product_id=None):
        """Get all reviews for a product"""
        product = self.get_object()
        reviews = product.reviews.filter(is_approved=True)

        page = self.paginate_queryset(reviews)
        if page is not None:
            serializer = ProductReviewSerializer(page, many=True)
            return self.get_paginated_response(serializer.data)

        serializer = ProductReviewSerializer(reviews, many=True)
        return Response(serializer.data)

    def _publish_event(self, event_type, product):
        """
        Publish product events to RabbitMQ
        This is a placeholder - implement actual RabbitMQ publishing
        """
        event_data = {
            'event_type': event_type,
            'product_id': product.product_id,
            'sku': product.sku,
            'name': product.name,
            'category': product.category,
            'price': str(product.price),
            'is_active': product.is_active,
            'stock_quantity': product.stock_quantity,
            'timestamp': product.updated_at.isoformat()
        }
        logger.info(f"Event published: {event_type} - Product: {product.sku}")
        # TODO: Implement actual RabbitMQ publishing
        # Example: rabbitmq_client.publish('product_events', event_data)


class ProductReviewViewSet(viewsets.ModelViewSet):
    """
    ViewSet for Product Review CRUD operations
    """
    queryset = ProductReview.objects.all()
    serializer_class = ProductReviewSerializer
    permission_classes = [AllowAny]

    def get_queryset(self):
        queryset = ProductReview.objects.all()

        # Filter by product
        product_id = self.request.query_params.get('product_id')
        if product_id:
            queryset = queryset.filter(product_id=product_id)

        # Filter by approval status
        is_approved = self.request.query_params.get('is_approved')
        if is_approved is not None:
            queryset = queryset.filter(is_approved=is_approved.lower() == 'true')
        else:
            # By default, only show approved reviews
            queryset = queryset.filter(is_approved=True)

        return queryset.order_by('-created_at')

    @action(detail=True, methods=['post'])
    def approve(self, request, pk=None):
        """Approve a review"""
        review = self.get_object()
        review.is_approved = True
        review.save()

        logger.info(f"Review {review.id} approved for product {review.product.sku}")

        return Response({
            'message': 'Review approved successfully',
            'review_id': review.id
        })

    @action(detail=True, methods=['post'])
    def reject(self, request, pk=None):
        """Reject/unapprove a review"""
        review = self.get_object()
        review.is_approved = False
        review.save()

        logger.info(f"Review {review.id} rejected for product {review.product.sku}")

        return Response({
            'message': 'Review rejected successfully',
            'review_id': review.id
        })