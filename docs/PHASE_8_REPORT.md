# FASE 8.10 — Certification Alignment & Schema Registry

IMPORTANTE

Esta fase NO agrega funcionalidades nuevas.

NO modifica OCR.

NO modifica Assembly.

NO modifica Segmenter.

NO modifica Continuity.

NO modifica Parser.

NO modifica Knowledge.

NO modifica Validator.

NO modifica Normalizer.

NO modifica Confidence.

NO modifica el pipeline V2.

Su único objetivo es garantizar que TODO el sistema habla exactamente el mismo lenguaje antes de pasar a la Fase 9.

------------------------------------------------------------
OBJETIVO
------------------------------------------------------------

Eliminar cualquier desalineación entre:

• Parser
• Knowledge Engine
• Validator
• Normalizer
• Confidence Engine
• Golden Dataset
• Regression Framework
• Certification Engine

Toda definición de campo debe existir en un único lugar.

Nunca debe existir un campo esperado por un módulo que ningún otro produzca.

------------------------------------------------------------
FASE 8.10.1 — Schema Registry
------------------------------------------------------------

Crear un nuevo módulo:

backend/app/v2/schema/

con:

__init__.py

field_registry.py

definitions.py

validation.py

coverage.py

models.py

------------------------------------------------------------

Crear una clase central:

FieldDefinition

con atributos como:

field_name

display_name

description

country

document_type

data_type

required

parser_supported

knowledge_supported

validator_supported

normalizer_supported

confidence_supported

golden_dataset_supported

certification_supported

aliases

regex_patterns

examples

deprecated

version

------------------------------------------------------------
FASE 8.10.2 — Registry Único
------------------------------------------------------------

TODOS los módulos deberán consultar este registro.

No más listas duplicadas.

No más nombres repetidos.

No más diccionarios independientes.

Parser

Knowledge

Validator

Golden Dataset

Certification

deben consumir exactamente el mismo catálogo.

------------------------------------------------------------
FASE 8.10.3 — Coverage Analyzer
------------------------------------------------------------

Crear un analizador automático.

Debe revisar todos los campos.

Ejemplo:

expediente

Parser ✔

Knowledge ✔

Validator ✔

Normalizer ✔

Golden ✔

Certification ✔

Coverage 100%

------------------------------------------------------------

Ejemplo:

fianza_porcentaje

Parser ✘

Knowledge ✘

Validator ✔

Golden ✔

Certification ✔

Coverage 40%

------------------------------------------------------------

Debe detectar automáticamente:

• campos huérfanos

• campos nunca producidos

• campos nunca consumidos

• campos duplicados

• nombres inconsistentes

• alias redundantes

------------------------------------------------------------
FASE 8.10.4 — Dependency Validation
------------------------------------------------------------

Validar automáticamente:

Quién produce cada campo.

Quién consume cada campo.

Quién lo modifica.

Quién lo valida.

Quién lo normaliza.

Quién lo certifica.

Generar un grafo de dependencias serializable.

------------------------------------------------------------
FASE 8.10.5 — Certification Alignment
------------------------------------------------------------

Modificar únicamente el Certification Engine.

NO modificar Parser.

NO modificar Validator.

NO modificar Knowledge.

Agregar nuevas validaciones:

• cobertura por campo

• cobertura por país

• cobertura por tipo documental

• cobertura por etapa

• campos críticos faltantes

------------------------------------------------------------

El sistema NO podrá devolver:

CERTIFIED

si existe:

- un campo crítico sin productor

- un campo obligatorio sin consumidor

- un campo requerido por Golden Dataset que ningún parser genere

------------------------------------------------------------
FASE 8.10.6 — Compatibility Checker
------------------------------------------------------------

Crear un comprobador automático.

Debe revisar:

Parser

Knowledge

Validator

Normalizer

Confidence

Golden Dataset

Regression

Certification

y confirmar:

compatible = TRUE/FALSE

Además indicar exactamente:

qué módulo

qué campo

qué problema

qué solución

------------------------------------------------------------
FASE 8.10.7 — Field Matrix
------------------------------------------------------------

Generar automáticamente una matriz como:

Campo

Tipo

PA

CO

Parser

Knowledge

Validator

Normalizer

Confidence

Golden

Certification

Cobertura

Obligatorio

Opcional

Estado

Todo exportable en JSON y Markdown.

------------------------------------------------------------
FASE 8.10.8 — Consistency Report
------------------------------------------------------------

Crear un reporte automático indicando:

Campos faltantes

Campos duplicados

Campos inconsistentes

Alias redundantes

Regex duplicadas

Dependencias rotas

Cobertura

Porcentaje de alineación

------------------------------------------------------------
FASE 8.10.9 — Auto Fix Suggestions
------------------------------------------------------------

NO modificar código automáticamente.

Solo generar recomendaciones.

Ejemplo:

Agregar campo:

fianza_porcentaje

en:

ColombiaRemateParser

porque es requerido por:

Golden Dataset

Validator

Certification

------------------------------------------------------------
FASE 8.10.10 — Tests
------------------------------------------------------------

Agregar pruebas nuevas.

No eliminar ninguna existente.

Agregar pruebas para:

Schema Registry

Coverage Analyzer

Dependency Validation

Compatibility Checker

Certification Alignment

Field Matrix

Consistency Report

Auto Fix Suggestions

El total de pruebas deberá superar las existentes.

------------------------------------------------------------
REGLAS
------------------------------------------------------------

Todo determinista.

Sin LLM.

Sin IA generativa.

Sin romper V1.

Sin romper V2.

Sin modificar interfaces públicas.

Sin duplicar definiciones.

Todo documentado.

Todo probado.

------------------------------------------------------------
ANTES DE IMPLEMENTAR
------------------------------------------------------------

Auditar TODO el código existente.

Reutilizar componentes.

Eliminar únicamente duplicidad lógica si existe.

No crear nuevas arquitecturas paralelas.

------------------------------------------------------------
AL FINAL
------------------------------------------------------------

Entregar un reporte completo con:

• Arquitectura implementada

• Componentes creados

• Integración

• Cobertura por campo

• Cobertura por país

• Cobertura por documento

• Compatibilidad entre módulos

• Problemas encontrados

• Recomendaciones

• Total de pruebas

• Estado final de alineación del motor

NO avanzar a la Fase 9.

La Fase 9 comenzará únicamente cuando el motor esté completamente alineado y certificado.