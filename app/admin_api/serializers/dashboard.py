from rest_framework import serializers


class ChartDefinitionResponseSerializer(serializers.Serializer):
    """단일 차트 정의 — 표시 메타 + 자기 data 엔드포인트/파라미터를 함께 담는다."""

    class ParameterSerializer(serializers.Serializer):
        class OptionSerializer(serializers.Serializer):
            value = serializers.JSONField()
            label = serializers.CharField()
            event_id = serializers.CharField(required=False, allow_null=True)  # 티켓 옵션의 소속 이벤트(종속 필터용)

        key = serializers.CharField()
        label = serializers.CharField()
        type = serializers.ChoiceField(
            choices=["date", "date_range", "select", "multi_select", "text", "number", "boolean"]
        )
        required = serializers.BooleanField()
        default = serializers.JSONField(required=False, allow_null=True)
        options = OptionSerializer(many=True, required=False, allow_null=True)

    class OptionsSerializer(serializers.Serializer):
        stacked = serializers.BooleanField(required=False, allow_null=True)
        show_legend = serializers.BooleanField(required=False, allow_null=True)
        x_axis_label = serializers.CharField(required=False, allow_null=True)
        y_axis_label = serializers.CharField(required=False, allow_null=True)
        value_format = serializers.CharField(required=False, allow_null=True)
        show_data_label = serializers.BooleanField(required=False, allow_null=True)

    id = serializers.CharField()
    title = serializers.CharField()
    type = serializers.ChoiceField(choices=["line", "bar", "pie", "metric"])
    unit = serializers.CharField(required=False, allow_null=True)
    options = OptionsSerializer(required=False, allow_null=True)
    endpoint = serializers.CharField()
    method = serializers.ChoiceField(choices=["GET", "POST"])
    params = ParameterSerializer(many=True)


class MetricChartDataResponseSerializer(serializers.Serializer):
    """metric 차트 — 단일 수치 (+ 선택적 전기간 대비)."""

    class ComparisonSerializer(serializers.Serializer):
        label = serializers.CharField()
        value = serializers.FloatField()
        unit = serializers.CharField(required=False, allow_null=True)
        direction = serializers.ChoiceField(choices=["up", "down", "flat"])

    chart_id = serializers.CharField()
    value = serializers.JSONField(allow_null=True)  # ChartValue: number | string | null
    comparison = ComparisonSerializer(required=False, allow_null=True)


class SeriesChartDataResponseSerializer(serializers.Serializer):
    """line / bar / pie 차트 — 시리즈 + 데이터 포인트."""

    class SeriesSerializer(serializers.Serializer):
        key = serializers.CharField()
        name = serializers.CharField()
        color = serializers.CharField(required=False, allow_null=True)

    class DataPointSerializer(serializers.Serializer):
        label = serializers.CharField()
        values = serializers.DictField(child=serializers.JSONField(), required=False, allow_null=True)
        value = serializers.JSONField(required=False, allow_null=True)  # pie 조각용
        color = serializers.CharField(required=False, allow_null=True)

    chart_id = serializers.CharField()
    series = SeriesSerializer(many=True)
    data = DataPointSerializer(many=True)


class ChartDataRequestSerializer(serializers.Serializer):
    # chart_id 는 URL(/charts/{id}/data/)로 전달되므로 body 에는 params 만.
    params = serializers.DictField(required=False, default=dict)
