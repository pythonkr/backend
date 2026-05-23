import pytest
from django.db import IntegrityError
from shop.product.models import Category, CategoryGroup, OptionGroup, Product, ProductTagRelation, Tag


@pytest.mark.django_db
def test_category_group_name_unique_constraint_rejects_duplicate():
    CategoryGroup.objects.create(name="기본")
    with pytest.raises(IntegrityError):
        CategoryGroup.objects.create(name="기본")


@pytest.mark.django_db
def test_category_unique_per_group_name_combination():
    group = CategoryGroup.objects.create(name="g")
    Category.objects.create(group=group, name="cat")
    with pytest.raises(IntegrityError):
        Category.objects.create(group=group, name="cat")


@pytest.mark.django_db
def test_category_same_name_allowed_across_different_groups():
    g1 = CategoryGroup.objects.create(name="g1")
    g2 = CategoryGroup.objects.create(name="g2")
    Category.objects.create(group=g1, name="cat")
    # 다른 group 의 같은 name 은 허용 — UniqueConstraint(fields=["group", "name"]).
    Category.objects.create(group=g2, name="cat")


@pytest.mark.django_db
def test_tag_name_unique_constraint_rejects_duplicate():
    Tag.objects.create(name="굿즈")
    with pytest.raises(IntegrityError):
        Tag.objects.create(name="굿즈")


@pytest.mark.django_db
def test_product_tag_relation_unique_per_product_tag_combination(product):
    t = Tag.objects.create(name="t")
    ProductTagRelation.objects.create(product=product, tag=t)
    with pytest.raises(IntegrityError):
        ProductTagRelation.objects.create(product=product, tag=t)


@pytest.mark.django_db
def test_option_group_unique_per_product_name_combination(product):
    OptionGroup.objects.create(product=product, name="옵션")
    with pytest.raises(IntegrityError):
        OptionGroup.objects.create(product=product, name="옵션")


@pytest.mark.django_db
def test_option_group_same_name_allowed_across_different_products(product):
    other = Product.objects.create(
        category=product.category,
        name="other",
        price=100,
        visible_starts_at=product.visible_starts_at,
        visible_ends_at=product.visible_ends_at,
        orderable_starts_at=product.orderable_starts_at,
        orderable_ends_at=product.orderable_ends_at,
        refundable_ends_at=product.refundable_ends_at,
    )
    OptionGroup.objects.create(product=product, name="옵션")
    # 다른 product 의 같은 name 은 허용.
    OptionGroup.objects.create(product=other, name="옵션")
