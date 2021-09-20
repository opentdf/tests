# ABACUS UI

#virtru #abacus

UI: https://virtru.invisionapp.com/console/Abacus-ckbgo1s2l01h2014t2hrsyllc

## Pages

### Attributes Page

#### Components

- [Page Header](#page-header)
- [Section Header](#section-header)
  - Title: Attributes
  - Subtitle Dictionary:
    - Attribute
    - Information attached to data and entities that controls which entities can access which data.
  - Actions:
    - New Attribute Button
- [Attributes](#attributes)

### Attribute Page

#### Components

- [Page Header](#page-header)
- [Section Header](#section-header)
  - Title
    - `"{{Attribute Rule Name}}"`
  - Breadcrumb:
    - Attributes
  - Subtitle Dictionary:
    - Attribute
    - Information attached to data and entities that controls which entities can access which data.
  - Actions:
    - [Edit Button](#edit-button)
    - [Delete Button](#delete-button)
- [Attribute Rule Card](#attribute-rule-card)

### Attribute Item Page

- Page Header
- Section Header
  - Title
    - `"{{Attribute Name}}"`
  - Breadcrumb
    - Attributes
    - {{Attribute Rule}}
  - Subtitle Dictionary:
    - Attribute
    - Information attached to data and entities that controls which entities can access which data.
  - Actions:
    - [Edit Button](#edit-button)
    - [Delete Button](#delete-button)
- Detail List
  - Item
    - Attribute URI
    - {{URI}}
  - Item
    - Key Access Service
    - {{KAS URL}}
  - Item
    - Public Key
    - {{Public Key}}
    - Info Icon
- Table
  - Table Header
    - `title="Entities with \"{{Attribute Rule Name}}:{{Attribute Name}}\""`
    - Actions
      - Button
        - `title="Assign Entity"`
        - `type="primary"`
  - Table Body
    - Item
      - Full Name
      - Email
      - Distinguished Name
      - Actions
        - Button
          - `title="Remove entity from attribute"`
  - Table Footer
    - `align="center"`
    - Button
      - `title="+ Assign entity to attribute"`
  - Table Pagination

### Entities Page

List of entities

### Settings Page

## Components

### Buttons

#### Button

**Props**

- `children: string|ReactNode`
- `onClick: function`
- `type: enum`
  - primary
  - danger
  - outline
  - link

**Components**

- `{{children}}`
- `className={{type}}`
- `onClick={{onClick}}`

#### Edit Button

**Props**

- `onClick: function`

**Components**

- Button
  - `children="Edit"`
  - `type="outline"`

#### Delete Button

**Props**

- `onDelete: function`
- `onCancel: function`
- `onClick: function`

**Components**

- Button
  - `children: "Delete"`
  - `type: "link"`

#### Remove Button

**Props**

- `onRemove: function`

**Components**

- Button
  - `children: "Remove"`
  - `type: "destructive"`

### Page Header

- Branding
  - Logo
  - ABACUS
- Links
  - [Attributes Link](#attributes-page)
  - [Entities Link](#entities-page)
  - [Settings Link](#settings-page)

### Section Header

- Title
- Subtitle Dictionary
- Action Buttons

### Ordered List Edit

- Label
- List
  - Order
  - Item[]
    - Order Action
      - Down
      - Up
    - Item

### Unordered List

- Label
- List
  - Item

### Attribute Edit List

**Props**

- `isOrdered = false`

**Component**

- Label
- List
  - [Attribute Item](#attribute-item)

### Attribute Item

**Props**

- `showOrderAction = false`
- `currentOrder: integer`
- `onOrderChange: function`

**Components**

- Order Action
  - Up Carrot
  - Down Carrot
- Title
- Detail
  - URI
  - Actions
    - Button - `"Entities & details"`

### Attribute Rule Card

- Header
  - Title
  - Buttons
    - Button
      - `"+ New Value"`
    - Button
      - `"Details"`
- Sub-header
  - Title
    - Permissive
    - Restrictive
    - Hierarchical
  - Buttons
    - Edit rule
- Items
  - [Attribute Item](#attribute-item)

### Attributes Edit Rule

- Header
  - Title: Edit rule
- Edit Card
  - Attribute Rule
    - Label
      - `"Attribute Rule"`
    - Selector
      - `options: []
        - Hierarchical Access
        -
    - Selector Description
      - `list: []
        - Entities must be **higher than or equal to** data in a hierarchy of attribute values.
        -
  - Heirarchy Rules
    - Ordered List Edit
      - Label: Current hierarchy
    - Ordered Rule Sandbox
  - Restrictive Rules - Label: Current attribute values
    - Unordered Rule Sandbox
  - Permissive Rules - Unordered List - Label: Current attribute values - Rule Sandbox - `type: "unordered"` - `attributes: {{Attributes}}`
- Footer
  - Actions
    - Button
      - `type: "outline"
      - `title: "Cancel"
    - Button
      - `type: "primary"`
      - `title: "Save rule"`

### Attributes

- Header
  - Authority Namespace Selector
- List
  - [Attribute Rule Card](#attribute-rule-card)

### Rule Sandbox

**Props**

- `type: emum {ordered, unordered}`
- `attributes: array`

**Components**

- Label
  - `"Rule sandbox"
- If List
  - Icon
  - Title: If data has
  - List
    - Action
      - Checkbox _if type is unordered_
      - Radio _if type is ordered_
    - Text: {{Attribute Name}}
- Then List
  - Icon
  - Title: and data has
  - List
    - Action
      - Checkbox _if type is unordered_
      - Radio _if type is ordered_
    - Text: {{Attribute Name}}
- Result Footer
  - Text: "then access would be"
  - Result
    - Denied _if result is denied_
      - Icon: Hand
      - "Denied"
    - Granted _if result is granted_
      - Icon: Open Eye
      - "Granted"

### Search

**Props**

- `resource: object{singular: string, plural: string}`
- `description: string`
- `action`

**Components**

- Title
- Search Field
  - Label
    - `"Search for an {{resource.singular}}"
  - Input
  - Actions
    - [Search Button](#search-button)
    - [Cancel Button](#cancel-button)`
  - Description
    - `{{description}}`
- [Search Results](#search-results)

### Search Results

**Props**

- `searchResults: array`
- `resource: object{singular: string, plural: string}`
- `actionTitle: string`
- `actionUnavailableMessage: string`
  - _When the resource is already added what does it say_
- `actionOnClick: function`

**Components**

- Title
  - `"Found {{searchResults.length}} {{resource.plural}}"`
- Result Table
  - Table Body
    - Available Entity
      - Name
      - Email
      - DN
      - Actions
        - Button _if resource.isAvailable_
          - `type: "link"`
          - `"{{actionTitle}}"`
          - `onClick: {{actionOnClick}}`
        - Notice
          - Icon
            - `type="checkmark-filled"`
          - `"{{actionUnavailableMessage}}"`

### Modal

**Props**

- `title: string|ReactNode`
- `description: string|null`
- `footerContent: ReactNode|null`

**Components**

- Header
  - `{{title}}`
- Body
  - `{{description}}`
- Footer
  - `{{actions}}`

#### Prompt Modal

**Props**

- `title: string|ReactNode`
- `description: string|null`
- `onCancel: function`
- `onOk: function`
- `okButton: object{text="Ok", type="primary"}`
- `cancelButton: object{text="Cancel", type="outline"}`

**Components**

- [Modal](#modal)
  - `title={{title}}`
  - `description={{description}}`
  - `footer=[]`
    - [Cancel Button](#cancel-button)
    - [Button](#remove-button)
      - `text="Ok"`
      - `onOk={{onOk}}`

#### Destructive Prompt Modal

**Props**

- `title: string|ReactNode`
- `description: string|null`
- `onCancel: function`
- `onRemove: function`

**Components**

- [Prompt Modal](#prompt-modal)
  - `title={{title}}`
  - `description={{description}}`
  - `actions=[]`
    - [Cancel Button](#cancel-button)
    - [Remove Button](#remove-button)
