"""
CSV 导出 Admin Mixin — 无外部依赖，直接流式导出
"""
import csv

from django.http import HttpResponse


class CSVExportMixin:
    """为 ModelAdmin 添加 CSV 导出功能"""

    csv_fields = None  # 子类覆盖：要导出的字段名列表
    csv_filename = 'export.csv'

    def export_as_csv(self, request, queryset):
        """导出选中记录为 CSV"""
        fields = self.csv_fields or [f.name for f in queryset.model._meta.fields]
        response = HttpResponse(content_type='text/csv; charset=utf-8-sig')
        response['Content-Disposition'] = f'attachment; filename="{self.csv_filename}"'
        response.write('﻿')  # BOM for Excel

        writer = csv.writer(response)
        writer.writerow(fields)

        for obj in queryset.iterator():
            row = []
            for field in fields:
                val = getattr(obj, field, '')
                if callable(val):
                    val = val()
                row.append(str(val) if val is not None else '')
            writer.writerow(row)

        return response

    export_as_csv.short_description = '导出选中为 CSV'
