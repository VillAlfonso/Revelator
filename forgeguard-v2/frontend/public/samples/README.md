# Category Sample Gallery

Drop curated training-set images here so end users can see what each forgery category looks like.

## Folder convention

```
samples/
├── traced/
│   ├── 1-annotated.jpg
│   ├── 1-original.jpg
│   ├── 2-annotated.jpg
│   ├── 2-original.jpg
│   ├── ...
│   └── 5-original.jpg
├── alteration/
├── digital/
├── obliteration/
├── sympathetic_ink/
└── currency/
```

- 5 pairs per category (`1`..`5`)
- Each pair: `<n>-annotated.jpg` (with bounding boxes drawn) + `<n>-original.jpg` (raw)
- Recommended: 800x600 or 4:3, JPEG quality ~85
- Missing files render as styled placeholders - won't break the page

## How-to-shoot guidance

Per-category tips and "what the detector looks for" strings live in
`frontend/src/pages/SampleGallery.jsx` (`GUIDANCE` map). Edit there.
