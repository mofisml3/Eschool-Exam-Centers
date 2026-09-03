# Project Instructions

This repository contains the complete specifications for the project.

Before writing any code, carefully review all documents inside `/docs`.

The documents are:

- `docs/Overview.md` — functional and system requirements
- `docs/requirements.md` — functional and system requirements
- `docs/business-rules.md` — business rules and workflows

## Development Rules

1. Do not start implementation before reviewing the specifications.
2. Create an implementation plan first.
3. Identify contradictions or missing requirements before coding.
4. Follow the architecture defined in the documentation.
5. Keep the implementation modular and maintainable and scalable.
6. Add appropriate tests.
7. Do not change core business requirements without explicitly identifying the change.

## Initial Task

When starting this repository:

1. Read all specification documents.
2. Analyze the system.
3. Propose the project architecture and directory structure.
4. Create a phased implementation plan.
5. Then begin implementation phase by phase.


1	منع كتابة أي معيار تشغيلي داخل الكود؛ كلها تُقرأ من جدول parameters	يجعل النظام ديناميكياً قابلاً للتعديل دون برمجة
2	كل دالة في محرك الطاقة أو التوزيع لها اختبار pytest قبل الانتقال	يمنع نظاماً يبدو أنه يعمل دون أن يعمل
3	القيود الإلزامية تُفرض في قاعدة البيانات وليس في الكود وحده	حماية البيانات من توزيع خاطئ أو مكرر
4	كل تشغيل توزيع يُحفظ كسيناريو مع لقطة من المعايير	يتيح المقارنة والتراجع والتدقيق
5	لا تُخزّن أي بيانات مالية في هذا النطاق	النطاق تشغيلي بحت؛ الكلفة تُعالج منفصلة
6	كل مرحلة تنتهي بتشغيل الاختبارات وإظهار النتيجة قبل المرحلة التالية	يمنع تراكم الأخطاء بين المراحل
