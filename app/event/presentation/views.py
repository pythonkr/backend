from event.presentation.models import Presentation
from event.presentation.serializers import PresentationSerializer
from rest_framework import mixins, viewsets


class PresentationViewSet(mixins.ListModelMixin, viewsets.GenericViewSet):
    queryset = Presentation.objects.get_all_nested_data()
    serializer_class = PresentationSerializer

    def get_queryset(self):
        if category_name := self.request.query_params.get("category"):
            return Presentation.objects.filter_by_category(category_name)
        return self.queryset
