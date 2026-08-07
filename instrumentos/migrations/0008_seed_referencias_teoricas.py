from django.db import migrations

REFERENCIAS = [
    {
        "titulo": "Modelo Demanda-Controle-Suporte (Karasek & Theorell)",
        "descricao": "Equilíbrio entre exigências do trabalho e recursos disponíveis ao trabalhador.",
        "ordem": 1,
    },
    {
        "titulo": "Modelo Esforço-Recompensa (Siegrist)",
        "descricao": "Proporção entre o esforço investido pelo trabalhador e o reconhecimento recebido.",
        "ordem": 2,
    },
    {
        "titulo": "Justiça organizacional e qualidade da liderança",
        "descricao": "Fatores moderadores reconhecidos pela literatura de saúde ocupacional.",
        "ordem": 3,
    },
]


def criar_referencias(apps, schema_editor):
    ReferenciaTeorica = apps.get_model("instrumentos", "ReferenciaTeorica")
    for dados in REFERENCIAS:
        ReferenciaTeorica.objects.get_or_create(titulo=dados["titulo"], defaults=dados)


def remover_referencias(apps, schema_editor):
    ReferenciaTeorica = apps.get_model("instrumentos", "ReferenciaTeorica")
    ReferenciaTeorica.objects.filter(titulo__in=[d["titulo"] for d in REFERENCIAS]).delete()


class Migration(migrations.Migration):

    dependencies = [
        ("instrumentos", "0007_referenciateorica_dominio_descricao_medicao_and_more"),
    ]

    operations = [
        migrations.RunPython(criar_referencias, remover_referencias),
    ]
