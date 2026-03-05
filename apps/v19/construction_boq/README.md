## construction_boq — Odoo 19

### Instalação

```bash
# 1. Copiar o módulo para a pasta addons do Odoo
cp -r construction_boq /path/to/odoo/addons/

# 2. Instalar dependência Python
pip install openpyxl

# 3. Actualizar lista de módulos no Odoo
# Settings → Technical → Update Apps List

# 4. Instalar o módulo
# Apps → Construction BOQ → Install
```

### Dependências Python
- `openpyxl` — importação e exportação Excel

### Estrutura de Dados

```
construction_obra          ← Obra / Empreitada
  └── construction_boq     ← Mapa de Quantidades (com revisões)
        └── construction_boq_capitulo    ← Capítulo
              └── construction_boq_subcapitulo  ← Subcapítulo
                    └── construction_boq_artigo ← Artigo (liga a product.product)
```

### Sistema de Revisões
- BOQ em `draft` → editável
- Ação "Partilhar" → estado `shared` → só leitura
- "Nova Revisão" cria cópia com versão+1, a anterior fica arquivada
- Gestores (`group_boq_manager`) podem editar BOQs partilhados

### Performance SQL
- Todas as operações CRUD no editor usam SQL parametrizado diretamente
- Queries nunca usam string interpolation com dados de utilizador
- Índices criados em: `boq_id`, `subcapitulo_id`, `capitulo_id`, `sequence`
- Deep copy de estrutura BOQ via INSERT ... SELECT (sem Python loop)

### Segurança
- Multi-company via record rules
- 3 grupos: Utilizador / Editor / Gestor
- BOQs em draft só visíveis pelo criador (a menos que partilhados)
- Todos os endpoints JSON validam acesso ao BOQ via ORM browse

### Roadmap
- [ ] Autos de Medição (construction.auto)
- [ ] Controlo Custos vs Orçamento
- [ ] Integração Autodesk ACC API
- [ ] Faturação a partir de Auto de Medição
- [ ] App mobile para medição em campo
