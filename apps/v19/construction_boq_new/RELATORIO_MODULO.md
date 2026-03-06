# Construction BOQ Manager — Relatório Técnico Detalhado

**Módulo:** `construction_boq`
**Versão:** 19.0.1.0.0
**Plataforma:** Odoo 19 (OWL 2, Python 3.12+)
**Data do relatório:** 2026-03-05
**Localização:** `custom_modules/construction_boq/`

---

## 1. Visão Geral

O módulo **Construction BOQ Manager** é uma aplicação completa de gestão de Mapas de Quantidades (Bills of Quantities) para projectos de construção, integrada nativamente no Odoo 19. Cobre o ciclo de vida completo de um BOQ — desde a criação e edição inline, passando pela partilha/bloqueio com revisões, até à exportação para clientes e relatórios PDF.

### Dependências Odoo
`base`, `mail`, `project`, `product`, `uom`, `purchase`, `sale_management`, `account`, `analytic`, `stock`, `contacts`, `web`

---

## 2. Estrutura de Ficheiros

```
construction_boq/
├── __init__.py
├── __manifest__.py
├── controllers/
│   ├── __init__.py
│   ├── main.py              # API JSON-RPC para o editor OWL
│   └── download.py          # Rotas HTTP para download de Excel
├── models/
│   ├── __init__.py
│   ├── construction_obra.py       # Modelo: Projecto de Construção
│   ├── construction_boq.py        # Modelo principal: BOQ
│   ├── construction_boq_capitulo.py  # Modelos: Capítulo e Sub-Capítulo
│   └── construction_boq_artigo.py    # Modelo: Artigo/Item
├── security/
│   ├── groups.xml              # Grupos, Privilege e ir.module.category
│   ├── ir.model.access.csv     # ACLs por grupo
│   └── record_rules.xml        # Regras de registo multi-empresa
├── views/
│   ├── construction_obra_views.xml
│   ├── construction_boq_views.xml
│   ├── construction_boq_artigo_views.xml
│   ├── construction_overview.xml
│   └── menus.xml
├── wizard/
│   ├── boq_wizards.py          # Export + Import wizards (openpyxl)
│   └── boq_wizard_views.xml
├── report/
│   ├── boq_report_templates.xml  # Template QWeb PDF
│   └── boq_report_actions.xml    # Acção de relatório
├── data/
│   └── sequence_data.xml       # Sequência automática ref_interna
└── static/src/
    ├── scss/boq_editor.scss
    └── components/boq_editor/
        ├── boq_editor.js       # Componente OWL principal
        └── boq_editor.xml      # Template OWL
```

---

## 3. Modelos de Dados

### 3.1 `construction.obra` — Projecto de Construção

**Tabela:** `construction_obra`
**Herança:** `mail.thread`, `mail.activity.mixin`

| Campo | Tipo | Descrição |
|---|---|---|
| `name` | Char | Nome do projecto (obrigatório) |
| `ref_interna` | Char | Referência interna (sequência automática) |
| `ref_concurso` | Char | Referência de concurso/tender |
| `partner_id` | Many2one `res.partner` | Cliente (obrigatório) |
| `partner_fiscalizacao_id` | Many2one `res.partner` | Fiscalização/Engenheiro |
| `user_id` | Many2one `res.users` | Gestor de Projecto |
| `company_id` | Many2one `res.company` | Empresa |
| `tipo_empreitada` | Selection | Direct Award / Public Tender / Market Consultation / Public Works |
| `tipo_obra` | Selection | New Build / Rehabilitation / HVAC / BMS / Electrical / Hydraulic / Infrastructure / Industrial / Maintenance / Mixed |
| `state` | Selection | prospect → proposal → awarded → in_progress → suspended → completed → warranty → closed |
| `date_start` | Date | Data de início contratual |
| `date_end_contract` | Date | Data de fim contratual |
| `date_end_forecast` | Date | Data de fim prevista |
| `date_awarded` | Date | Data de adjudicação |
| `currency_id` | Many2one | Moeda |
| `valor_contrato` | Monetary | Valor do contrato (ex. IVA) |
| `retencao_pct` | Float | Percentagem de retenção (default 5%) |
| `analytic_account_id` | Many2one | Centro de custo analítico |
| `boq_ids` | One2many | BOQs associados |
| `boq_active_id` | Many2one (computed) | BOQ activo (shared ou último draft) |
| `boq_count` | Integer (computed) | Número de BOQs |
| `street`, `city`, `zip`, `country_id` | — | Endereço da obra |
| `acc_project_id` | Char | ID Projecto Autodesk ACC |
| `acc_project_url` | Char | URL Autodesk ACC |

**Métodos:**
- `action_open_boq_list()` — abre lista de BOQs do projecto

---

### 3.2 `construction.boq` — Bill of Quantities

**Tabela:** `construction_boq`
**Herança:** `mail.thread`, `mail.activity.mixin`
**Ordenação:** `obra_id, version desc`

| Campo | Tipo | Descrição |
|---|---|---|
| `obra_id` | Many2one `construction.obra` | Projecto (cascade) |
| `name` | Char | Nome do BOQ |
| `version` | Integer | Número de versão (readonly) |
| `revision_label` | Char (computed) | Ex: "Rev.01", "Rev.02" |
| `state` | Selection | `draft` / `shared` / `archived` |
| `is_active_revision` | Boolean | Revisão activa do projecto |
| `parent_revision_id` | Many2one `construction.boq` | Revisão anterior |
| `child_revision_ids` | One2many | Revisões subsequentes |
| `date_created` | Datetime | Data de criação (readonly) |
| `date_shared` | Datetime | Data de partilha |
| `date_archived` | Datetime | Data de arquivo |
| `user_id` | Many2one `res.users` | Criado por |
| `shared_by_id` | Many2one `res.users` | Partilhado por |
| `notes` | Text | Notas livres |
| `currency_id` | Many2one (related obra) | Moeda |
| `total_boq` | Monetary (computed SQL) | Total do BOQ |
| `capitulo_count` | Integer (computed SQL) | Número de capítulos |
| `artigo_count` | Integer (computed SQL) | Número de artigos |

**Transições de estado:**

```
draft ──[action_share]──► shared ──[action_new_revision]──► (cria novo draft)
  ▲                                                               │
  └─────────────[action_reset_to_draft]──── archived ◄───────────┘
```

**Métodos principais:**

| Método | Descrição |
|---|---|
| `action_share()` | Bloqueia o BOQ (draft → shared), regista no chatter |
| `action_new_revision()` | Cria nova revisão (version+1) com deep copy SQL da estrutura |
| `action_archive_boq()` | Arquiva o BOQ |
| `action_reset_to_draft()` | Repõe estado draft (só archived) |
| `action_open_editor()` | Abre o editor OWL como `ir.actions.client` |
| `write()` | Guard: impede edição de conteúdo em BOQs shared/archived (exceto managers) |
| `_sql_deep_copy_structure()` | Copia capítulos → sub-capítulos → artigos via SQL puro (eficiente para 10k+ artigos) |
| `sql_load_boq_tree()` | Carrega árvore completa (capítulos + sub-capítulos + totais) via SQL |
| `sql_load_artigos()` | Carrega artigos paginados com filtro de pesquisa |
| `sql_save_artigo()` | INSERT ou UPDATE de artigo via SQL parametrizado |
| `sql_delete_artigo()` | Soft-delete de artigo (active=FALSE) |
| `sql_add_capitulo()` | Cria capítulo via SQL |
| `sql_add_subcapitulo()` | Cria sub-capítulo via SQL |
| `build_ai_context()` | Gera resumo textual do BOQ para o assistente AI |
| `_compute_totals_sql()` | Calcula totais/counts via SQL agregado |

> **Nota de performance:** Toda a leitura e escrita de dados do editor é feita via SQL directo (`cr.execute`), evitando o overhead do ORM para ficheiros com 10.000+ artigos.

---

### 3.3 `construction.boq.capitulo` — Capítulo

**Tabela:** `construction_boq_capitulo`

| Campo | Tipo | Descrição |
|---|---|---|
| `boq_id` | Many2one | BOQ pai (cascade) |
| `code` | Char | Código (ex: "01", "143") |
| `name` | Char | Nome do capítulo |
| `sequence` | Integer | Ordenação |
| `specialty` | Selection | General / Structure / HVAC / BMS / Electrical / Hydraulic / Fire / External / Foundations / Architecture / Maintenance |
| `color` | Char | Cor hex (default `#1E3A5F`) |
| `notes` | Text | Notas |
| `analytic_account_id` | Many2one | Centro de custo analítico |
| `subcapitulo_ids` | One2many | Sub-capítulos |

### 3.4 `construction.boq.subcapitulo` — Sub-Capítulo

**Tabela:** `construction_boq_subcapitulo`

| Campo | Tipo | Descrição |
|---|---|---|
| `boq_id` | Many2one | BOQ pai (cascade) |
| `capitulo_id` | Many2one | Capítulo pai (cascade) |
| `code` | Char | Código (ex: "01.02", "143.01") |
| `name` | Char | Nome |
| `sequence` | Integer | Ordenação |
| `notes` | Text | Notas |
| `artigo_ids` | One2many | Artigos |

### 3.5 `construction.boq.artigo` — Artigo/Item

**Tabela:** `construction_boq_artigo`

| Campo | Tipo | Descrição |
|---|---|---|
| `boq_id` | Many2one | BOQ pai (cascade) |
| `capitulo_id` | Many2one | Capítulo (cascade) |
| `subcapitulo_id` | Many2one | Sub-capítulo (cascade) |
| `code` | Char | Código do artigo (ex: "01.02.003") |
| `name` | Char | Descrição (obrigatório) |
| `sequence` | Integer | Ordenação |
| `active` | Boolean | Soft-delete flag |
| `product_id` | Many2one `product.product` | Produto Odoo (opcional) |
| `product_categ_id` | Many2one (related) | Categoria do produto |
| `uom_id` | Many2one `uom.uom` | Unidade de medida |
| `qty_contract` | Float (16,3) | Quantidade contratada |
| `price_unit` | Float (16,4) | Preço unitário |
| `obs` | Char | Observações/notas |
| `show_in_stock` | Boolean | Mostrar no painel de stock |
| `qty_on_hand` | Float (computed) | Stock disponível (via SQL sobre stock_quant) |
| `total_contract` | Monetary (computed) | qty × price_unit |

**Onchange:** ao seleccionar `product_id`, preenche automaticamente `uom_id`, `name` e `price_unit`.

---

## 4. Segurança e Controlo de Acesso

### 4.1 Grupos (Odoo 19 — `res.groups.privilege`)

**Categoria:** `ir.module.category` "Construction" (aparece como secção no separador Access Rights)
**Privilege:** `res.groups.privilege` "BOQ"

| Grupo (XML ID) | Nome | Herda de |
|---|---|---|
| `group_boq_user` | User | `base.group_user` |
| `group_boq_editor` | Editor | `group_boq_user` |
| `group_boq_manager` | Manager | `group_boq_editor` |

### 4.2 ACLs (`ir.model.access.csv`)

| Modelo | User | Editor | Manager |
|---|---|---|---|
| `construction.obra` | R | R/W/C | R/W/C/D |
| `construction.boq` | R | R/W/C | R/W/C/D |
| `construction.boq.capitulo` | R | R/W/C/D | R/W/C/D |
| `construction.boq.subcapitulo` | R | R/W/C/D | R/W/C/D |
| `construction.boq.artigo` | R | R/W/C/D | R/W/C/D |
| Export Wizard | R/W/C/D | — | — |
| Import Wizard | — | R/W/C/D | — |

### 4.3 Record Rules

| Regra | Grupos | Descrição |
|---|---|---|
| `rule_boq_company` | User | Só vê BOQs da sua empresa |
| `rule_boq_draft_own` | User | Lê só BOQs shared/archived OU os seus drafts |
| `rule_boq_editor_all` | Editor | Vê todos os BOQs da empresa |
| `rule_obra_company` | User | Só vê projectos da sua empresa |

### 4.4 Write Guard no Modelo

O método `write()` em `construction.boq` bloqueia alterações de conteúdo (campos não-meta) em BOQs com estado `shared` ou `archived`, excepto para utilizadores com papel `group_boq_manager`.

---

## 5. Editor OWL — Interface Principal

### 5.1 Componente: `BOQEditorAction`

**Ficheiro:** `static/src/components/boq_editor/boq_editor.js`
**Template:** `static/src/components/boq_editor/boq_editor.xml`
**Registado como:** `registry.category("actions").add("construction_boq.editor", BOQEditorAction)`

O editor é uma **client action** OWL 2 de três colunas:

```
┌─────────────────────────────────────────────────────────────┐
│  TOP BAR: título BOQ | estado | botões acção                │
├──────────────┬──────────────────────────────┬───────────────┤
│  LEFT: Tree  │  CENTRE: Tabela de artigos   │  RIGHT: AI    │
│  Capítulos   │  breadcrumb + pesquisa        │  (opcional)   │
│  Sub-caps    │  tabela inline editável       │               │
│  Totais      │  paginação + totais           │               │
└──────────────┴──────────────────────────────┴───────────────┘
```

**Estado reactivo (`useState`):**

| Chave | Tipo | Descrição |
|---|---|---|
| `loading` | Boolean | Estado de carregamento inicial |
| `tree` | Object/null | Árvore de capítulos carregada |
| `readonly` | Boolean | BOQ bloqueado (shared/archived) |
| `selectedCapId` | Integer | Capítulo seleccionado |
| `selectedSubId` | Integer | Sub-capítulo seleccionado |
| `articles` | Array | Artigos da página actual |
| `articlesTotal` | Integer | Total de artigos no sub-cap |
| `page`, `pageSize` | Integer | Paginação (150 por página) |
| `search` | String | Filtro de pesquisa |
| `capTotals`, `subTotals` | Object | Totais por capítulo/sub-cap |
| `grandTotal` | Float | Total geral do BOQ |
| `showStock` | Boolean | Coluna stock visível |
| `uoms` | Array | Lista de UoMs disponíveis |
| `aiOpen`, `aiMessages`, `aiLoading`, `aiInput` | — | Estado do assistente AI |

**Métodos principais (arrow functions para preservar `this`):**

| Método | Tipo | Descrição |
|---|---|---|
| `selectSub` | async arrow | Selecciona sub-capítulo e carrega artigos |
| `saveCell` | async arrow | Guarda célula editada (UPDATE via RPC) |
| `onUomChange` | arrow | Trata mudança de UoM no select |
| `deleteArticle` | async arrow | Soft-delete de artigo (com confirmação) |
| `addSubChapterById` | async arrow | Adiciona sub-capítulo por ID de capítulo |
| `sendSuggested` | async arrow | Envia pergunta sugerida ao AI |
| `addArticle` | async | Cria novo artigo no sub-cap seleccionado |
| `addChapter` | async | Cria novo capítulo (via prompt) |
| `exportClient` | — | Download Excel cliente |
| `openImport` | — | Abre wizard de importação |
| `toggleAI` | — | Mostra/oculta painel AI |
| `sendAI` | async | Envia pergunta ao AI (Odoo AI → OpenAI → built-in) |

**Funcionalidade F5 / Reload:**
- `boq_id` lido de: `action.context.boq_id` → `action.state.boq_id` → parse da URL pathname
- Persiste via `updateActionState({ boq_id })` após carregamento

**Sub-template Cell:**
Template `construction_boq.Cell` — célula inline editável/readonly, `readonly` passado explicitamente via `t-set` em cada `t-call` (compatibilidade OWL 2, sem `__context__`).

---

## 6. API JSON-RPC (Controller)

**Ficheiro:** `controllers/main.py`
**Classe:** `BOQController`
**Tipo de rotas:** `type='jsonrpc'`, `auth='user'`

| Rota | Método | Descrição |
|---|---|---|
| `/construction_boq/load_tree` | POST | Carrega árvore capítulos+sub-caps com totais |
| `/construction_boq/load_artigos` | POST | Carrega artigos paginados (offset, limit, search) |
| `/construction_boq/save_artigo` | POST | Cria ou actualiza artigo |
| `/construction_boq/delete_artigo` | POST | Soft-delete de artigo |
| `/construction_boq/add_capitulo` | POST | Cria novo capítulo |
| `/construction_boq/add_subcapitulo` | POST | Cria novo sub-capítulo |
| `/construction_boq/search_products` | POST | Pesquisa produtos Odoo (autocomplete) |
| `/construction_boq/search_uoms` | POST | Pesquisa unidades de medida |
| `/construction_boq/get_totals` | POST | Recalcula totais (cap, sub, grand) |
| `/construction_boq/ai_query` | POST | Consulta ao assistente AI |

**Download HTTP** (`controllers/download.py`):

| Rota | Descrição |
|---|---|
| `GET /construction_boq/export/<boq_id>` | Download Excel interno |
| `GET /construction_boq/export_client/<boq_id>` | Download Excel para cliente |

---

## 7. Assistente AI Integrado

**Endpoint:** `/construction_boq/ai_query`

O assistente funciona com fallback em cascata:

```
1. Odoo 19 LLM Provider (llm.provider ou mail.ai.provider)
        ↓ (se não disponível)
2. OpenAI API (chave em ir.config_parameter: openai.api_key ou ai.api_key)
        ↓ (se não disponível)
3. Motor built-in (análise de keywords, sempre disponível)
```

**Motor built-in** — detecta intenção por keywords:
- `total / value / cost / amount` → breakdown de totais por capítulo
- `chapter / breakdown / structure` → lista todos os capítulos
- `largest / biggest / top` → top 3 capítulos por valor
- `article / item / count / how many` → contagens por capítulo
- `specialty / hvac / bms / electrical` → agrupamento por especialidade

O contexto enviado ao AI inclui: nome do projecto, nome/revisão/estado do BOQ, total, número de artigos, e lista de capítulos com subtotais e percentagens.

---

## 8. Export / Import Excel

### 8.1 Export (`BOQExportWizard`)

**Modelo:** `construction.boq.export.wizard`
**Libraria:** `openpyxl`

**Dois modos:**
- **Interno:** completo, com colunas de stock opcionais e cores
- **Cliente:** simplificado, sem dados internos

**Formato do Excel gerado:**
- Linha de título com nome do projecto e revisão
- Linha de cabeçalho de colunas
- Linhas de capítulo (fundo azul escuro `#1E3A5F`, bold branco)
- Linhas de sub-capítulo (fundo `#243B55`, texto `#BAD8F5`)
- Linhas de artigo (zebra striping: branco / cinza claro)
- Linha de total por capítulo
- Linha de total geral
- Colunas: Código | Descrição | Un. | Quantidade | P.U. (€) | Total (€) | Observações [| Stock]

**Colunas com larguras automáticas** via `get_column_letter`.

**Acesso directo por URL** (sem abrir wizard):
- `GET /construction_boq/export/<id>` — download imediato interno
- `GET /construction_boq/export_client/<id>` — download imediato cliente

### 8.2 Import (`BOQImportWizard`)

**Modelo:** `construction.boq.import.wizard`
**Libraria:** `openpyxl` (read_only + data_only para performance)

**Dois modos:**
- **Substituir tudo:** apaga toda a estrutura existente (artigos → sub-caps → caps, por ordem FK) antes de importar
- **Adicionar ao existente:** acrescenta à estrutura já presente

**Formato esperado (coluna A):**
- `01` / `143` → header de capítulo (1-3 dígitos)
- `01.02` / `143.01` → header de sub-capítulo (1-3 dígitos . 2 dígitos)
- `01.02.003` / `143.01.015` → artigo (código com 3 partes)
- Colunas: A=Código | B=Descrição | C=Unidade | D=Qtd | E=P.U. | F=Total (ignorado) | G=Notas

**Fluxo:**
1. **Preview** — mostra capítulos detectados e primeiras 5 linhas
2. **Import** — insere via SQL parametrizado com pre-cache de UoMs (evita N queries para ficheiros grandes)

**Suporte a ficheiros grandes:** testado com 28.440 artigos e 143 capítulos.

---

## 9. Relatório PDF

**Template:** `report/boq_report_templates.xml`
**Acção:** `ir.actions.report` QWeb PDF
**Nome do relatório:** `construction_boq.report_boq_document`
**Nome do ficheiro:** `BOQ_<ref_interna>_<revision_label>.pdf`
**Binding:** associado ao modelo `construction.boq` (aparece no menu "Imprimir")

---

## 10. Vistas e Menus

### Vistas de `construction.obra`

- **Form view** — dados completos: identidade, parceiros, classificação, datas, financeiros, BOQs, localização, Autodesk ACC, chatter
- **List view** — colunas: ref_interna, nome, cliente, gestor, estado, data início, total BOQ activo
- **Search view** — filtros: In Progress, Awarded, Proposals, Completed, Public Tenders; Group By: Type, Status, Manager

### Vistas de `construction.boq`

- **Form view** — inclui botões: Open Editor (btn-primary), Share, New Revision, Archive, Reset to Draft; campos de identidade, revisão, datas, notas; Smart buttons: capítulos, artigos, total
- **List view** — colunas: projecto, revisão, estado, criado por, total, artigos
- **Search view** — filtros: Draft, Shared, Archived, Active Revision; Group By: Project, Status

### Vistas de `construction.boq.artigo`

- **Form view** — detalhe de artigo com integração Odoo product
- **List view** — tabela de artigos com BOQ pai

### Menus

```
Construction BOQ (app)
├── Projects           → lista construction.obra
└── Bills of Quantities → lista construction.boq
```

---

## 11. Dados e Sequências

**`data/sequence_data.xml`:**
- Sequência `construction.obra` para geração automática de `ref_interna` (prefixo `OBRA/`, padding 5, incremento 1)

---

## 12. Bugs Corrigidos / Decisões Técnicas

| # | Problema | Solução |
|---|---|---|
| 1 | `res.groups.category_id` removido em Odoo 19 | Migrado para `res.groups.privilege` + `ir.module.category` |
| 2 | `(4, ref(...))` deprecated | Substituído por `Command.link(ref(...))` em todo o módulo |
| 3 | `<group expand="0" string="...">` inválido em search views Odoo 19 | Substituído por `<group name="group_by">` |
| 4 | `type='json'` deprecated | Migrado para `type='jsonrpc'` em todas as rotas |
| 5 | `__context__` não existe em OWL 2 sub-templates | `readonly` passado explicitamente via `t-set` em cada `t-call` |
| 6 | Métodos chamados sem `this.` em event handlers OWL 2 | Convertidos para arrow function class fields |
| 7 | Import "Substituir tudo" mantinha estrutura antiga | Corrigido: DELETE artigos → sub-caps → caps antes do import |
| 8 | Import parava no capítulo 99 | Regex `\d{2}` → `\d{1,3}` (suporte a 100-999) |
| 9 | F5 no editor perdia o `boq_id` do contexto | Fallback: `action.state` + parse do URL pathname |
| 10 | Grupos BOQ não apareciam no separador Access Rights | Adicionados `ir.module.category` + `res.groups.privilege` |

---

## 13. Limitações Conhecidas / Melhorias Futuras

- **Stock em tempo real:** o campo `qty_on_hand` não é reactivo no editor (só no form view ORM)
- **Edição de capítulos/sub-capítulos inline:** o editor OWL não suporta renomear capítulos/sub-caps existentes (apenas criar novos)
- **Múltiplas moedas:** o BOQ herda a moeda do projecto; sem conversão automática
- **Relatório PDF:** template básico — pode ser expandido com layout mais detalhado
- **AI:** sem streaming de resposta; timeout de 20s para OpenAI
- **Import:** não detecta automaticamente formatos Excel com mais de 7 colunas (coluna G = observações fixo)

---

## 14. Requisitos de Instalação

```bash
# Dependência Python obrigatória para Export/Import Excel
pip install openpyxl

# Activar em Odoo
# Adicionar ao addons_path em odoo.conf:
# addons_path = ...,C:\Users\Utilizador\Desktop\odoo\V19\odoo\custom_modules

# Instalar/Actualizar
# Interface: Settings > Apps > Construction BOQ Manager > Install
# CLI: python odoo-bin -u construction_boq -d <database>
```

**Para AI com OpenAI:**
```
Settings > Technical > System Parameters
Criar: openai.api_key = sk-...
```

---

*Relatório gerado automaticamente em 2026-03-05*
