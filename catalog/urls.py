from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import CategoryViewSet, ProductViewSet

router = DefaultRouter()
router.register(r'categories', CategoryViewSet, basename='category')
router.register(r'products', ProductViewSet, basename='product')

urlpatterns = [
    path('v1/', include(router.urls)),
]

# Available endpoints:
# GET    /v1/categories/                - List all categories
# POST   /v1/categories/                - Create category
# GET    /v1/categories/{id}/           - Get category details
# PUT    /v1/categories/{id}/           - Update category
# PATCH  /v1/categories/{id}/           - Partial update category
# DELETE /v1/categories/{id}/           - Delete category
# GET    /v1/categories/{id}/products/  - Get products in category
#
# GET    /v1/products/                  - List all products
# POST   /v1/products/                  - Create product
# GET    /v1/products/{id}/             - Get product details
# PUT    /v1/products/{id}/             - Update product
# PATCH  /v1/products/{id}/             - Partial update product
# DELETE /v1/products/{id}/             - Soft delete product
# GET    /v1/products/search/           - Search products
# GET    /v1/products/featured/         - Get featured products