# Course Visual Generation and Insertion Prompt

Use the prompt below to design, generate, and insert instructional visuals into additional module course Markdown files. It captures the placement criteria, subject matter, visual language, and Markdown conventions validated for `real-time-analytics / level-1 / module-1`.

## Reusable Prompt

```text
You are creating instructional visuals for an English-language VeloDB / Apache Doris course.

Target course Markdown:
<COURSE_MD_PATH>

Module identifier:
<MODULE_ID>

Read the entire target Markdown file, then complete the full workflow: analyze candidate locations, generate the visuals, insert them into the Markdown, and verify the result. Do not infer the course content from the title alone, and do not rewrite unrelated course text.

1. Select the visual locations

1. Choose three to five places where a visual would provide the most learning value. Use fewer than five for short content; never add visuals merely to meet a quota.
2. Prioritize content such as:
   - A core concept that is introduced for the first time and is difficult to model mentally from text alone.
   - Data, query, or control-signal flows that pass through several components.
   - The position of Apache Doris in a system or data pipeline.
   - Responsibility boundaries among FE, BE, storage, clients, and external systems.
   - Comparisons between architectures, execution strategies, or design choices.
   - Stage changes from ingestion and organization through execution and result delivery.
   - Existing ASCII or text-based diagrams that would be clearer as an image.
3. Do not add redundant visuals for ordinary definitions, simple lists, a single SQL statement, procedural steps, or passages already explained adequately by nearby content.
4. Give each image one explicit teaching objective. It should primarily help the learner answer one of these questions: Where is the data? Which component is responsible? What happens next? How do the alternatives differ?
5. Before generating images, provide a short plan for each one that includes:
   - Insertion anchor: the paragraph or subsection after which it should appear.
   - Visual topic.
   - Components and arrow relationships.
   - What the image explains in that passage.
   - Suggested filename and aspect ratio.
6. Every fact, component name, and arrow direction must be supported by the course text. Do not introduce capabilities, performance figures, deployment components, or causal claims that the course does not teach.

2. Follow one visual language

All images must use the restrained, clear, engineering-oriented visual language of the dark technical flow diagrams on the VeloDB website. Do not create marketing posters or generic AI illustrations.

Mandatory requirements:

- Use a solid black background. Do not use textures, photographs, background grids, gradients, or decorative light effects.
- Render every Apache Doris core node as a solid dark-blue rectangular block.
- Put only `APACHE DORIS` inside a Doris block. Do not use the Apache Doris logo, write `VELODB ENGINE`, or add any other logo.
- Do not apply gradients, glass effects, perspective, or complex textures to Doris blocks.
- Use black or very dark-gray cards, thin outlines, and simple line icons for other systems, data sources, clients, tables, nodes, and results.
- Use VeloDB electric blue for the primary flow arrows and important connections. Use low-contrast blue-gray for secondary borders.
- Use white or near-white for primary text, cool gray for supporting text, and blue sparingly for emphasis.
- Use a flat, front-facing, two-dimensional composition. Do not use 3D, isometric views, character illustrations, photorealistic devices, or photographs.
- Keep borders thin, corner radii subtle, and whitespace generous. Avoid large shadows, glow, neon, and excessive decoration.
- Compose each image for embedding in course content. The primary flow must remain legible both at desktop width and when the image is scaled down.
- Prefer approximately 16:9 for ordinary concept diagrams and approximately 2.5:1 for horizontal flows or side-by-side comparisons. Do not combine several images into a montage.

Text requirements:

- Use English labels and match the terminology in the English course text.
- Keep labels short and explicit. Prefer noun phrases or verb phrases; do not place long paragraphs inside an image.
- Verify every technical term, capitalization choice, and spelling, including `APACHE DORIS`, `Frontend (FE)`, `Backend (BE)`, `CDC`, and `SQL`.
- Do not include garbled text, pseudo-text, clipped text, duplicate labels, or meaningless fine print.
- Do not add image numbers, filenames, watermarks, page numbers, or the word “Figure” to the canvas.

3. Organize each diagram

1. Arrange a flow in the actual order described by the course, normally from left to right or from top to bottom.
2. When Apache Doris is the subject of the lesson, make it the visual center without implying that it is the only component if the text does not say so.
3. For comparisons, use clear left/right or top/bottom regions and keep both sides at the same visual scale.
4. In architecture diagrams, distinguish clients, coordination and planning, execution, storage, and results. Avoid crossing arrows and ambiguous connections.
5. For data-organization concepts, show relationships among columns, shards, partitions, tablets, nodes, or stages instead of relying on decorative abstract shapes.
6. A short title and subtitle may clarify the purpose of a diagram. Omit them when the surrounding text already provides enough context and use the space for the structure itself.
7. The main nodes, direction, and conclusion must remain immediately recognizable after the image is scaled to the course content width.

4. Save the files and insert them into Markdown

1. Generate each visual as a separate, full-quality PNG source file.
2. Keep all generated source files and intermediate compression attempts outside the repository. Use the operating system's temporary directory, for example:
   `/tmp/doris-course-visuals/<MODULE_ID>/`
   Do not generate uncompressed source files directly under the target module.
3. After visual review and compression, copy only the final web-ready files into the target module at:
   `images/`
4. Use a two-digit sequence followed by an English kebab-case name, for example:
   `01-ingestion-paths.png`
   `02-fe-be-query-flow.png`
5. Number the files in the order in which they appear in the course.
6. Insert each image using a relative Markdown path, for example:

   ![A client sends SQL to FE, which plans distributed work for BE nodes and returns the combined result.](images/02-fe-be-query-flow.png)

   *FE plans and coordinates the query while BE nodes execute the distributed work.*

7. Write objective alt text that describes the relationship shown in the image. Do not use generic text such as `diagram` or `architecture`, and do not repeat the filename.
8. Add one italicized English caption below the image that states the conclusion the learner should take from it. Do not repeat the surrounding prose.
9. Normally place a visual after one or two paragraphs have introduced the relevant concept and before the next subsection heading. Do not place it between a heading and its opening paragraph unless it is genuinely an overview of the entire subsection.
10. If the source contains an ASCII or text diagram expressing the same relationship, replace that code block with the image and one caption while retaining the explanatory prose around it.
11. If no ASCII diagram exists, add only the image and caption. Do not delete or rewrite the course text.
12. Do not modify labs, quizzes, notebooks, course logic, or files outside the target course.
13. Do not edit the synchronized copy under `apps/web/app/courses/content/` in the website repository. Modify only the Markdown and image assets in the course source repository.
14. Delete the temporary source and intermediate files only after the compressed assets, Markdown paths, and rendered result have been verified. Never commit temporary or uncompressed variants.

5. Compress the final assets to approximately 100 KB

Follow the Apache Doris Website [Image Compression Guide](https://github.com/apache/doris-website/blob/master/doc-tools/prompts/img-compression-guide.md).

1. Target approximately 100 KB per final image. Aim for 80–120 KB; allow up to 150 KB only when further compression would make labels, thin lines, or arrows difficult to read.
2. These course diagrams rely on a solid black background, sharp text, and line art. Following the guide's solid-color-image rule, retain PNG and compress it with [TinyPNG](https://tinypng.com/).
3. If an exceptional image does not rely on a solid-color or transparent background, it may be converted to JPEG with Pillow using `convert('RGB')`, `quality=85`, and `optimize=True`, as specified by the guide. Use a `.jpg` filename and update the Markdown path accordingly.
4. If a TinyPNG-compressed PNG remains above 120 KB, reduce its pixel dimensions proportionally and compress it again. Preserve the required aspect ratio and do not stretch or crop the diagram.
5. Compare the compressed result with the reviewed source at the intended course-content width. The compressed version must preserve readable labels, clean arrows, accurate colors, and an apparently solid black background.
6. Record the final byte size of every asset. Only the compressed final file may be copied to `images/` and committed. Keep screenshots, generated diagrams, and other course illustrations together in this module-local directory.

6. Verify image quality

Inspect every generated image and confirm:

- The background is solid black.
- Every Apache Doris node is a solid dark-blue block containing only `APACHE DORIS`.
- No Doris logo, VeloDB logo, or `VELODB ENGINE` label appears.
- Technical names, arrow directions, and causal relationships agree with the course.
- There is no misspelling, pseudo-text, overlap, clipping, or text that is too small to read.
- Line widths, colors, card shapes, and spacing are consistent across the set.
- The visual genuinely reduces the effort required to understand the passage.
- The final asset is approximately 100 KB, normally within the 80–120 KB target range.
- Every Markdown relative path is correct and resolves to an existing file.
- Image order, file numbering, alt text, and captions correspond to one another.
- No uncompressed source, intermediate attempt, or backup image is present in the repository.

Regenerate any image that fails these checks. Do not repair it by covering text in post-processing, stretching the image, or explaining an error in the Markdown.

7. Report the result

At completion, provide:

1. A list of all added images, including each final format and file size.
2. The section where each image was inserted and its teaching purpose.
3. The path of every modified course Markdown file.
4. A statement identifying any ASCII or text diagram that was replaced.
5. A statement identifying related files that were deliberately left unchanged, such as labs, quizzes, and other modules.
```

## Addendum for Generating One Image at a Time

When the image-generation tool must be called separately for each image, append this template to the reusable prompt:

```text
Generate only image <N> in this call. Do not create a montage or a collection of alternatives.

Learning objective:
<THIS_IMAGE_LEARNING_GOAL>

Composition and flow:
<COMPONENTS_AND_FLOW>

Required English labels:
<REQUIRED_LABELS>

Forbidden or unsupported content:
<FORBIDDEN_OR_UNSUPPORTED_ELEMENTS>

Output aspect ratio:
<16:9_OR_WIDE>

Reminder: use a solid black background. Render every Apache Doris node as a solid dark-blue rectangular block containing only `APACHE DORIS`, with no logo. Keep all other components consistent with the dark technical flow-diagram style of the VeloDB website.
```

## Usage Notes

- Replace `<COURSE_MD_PATH>` with the actual Markdown path in the course source repository.
- Set `<MODULE_ID>` to the course, level, and module, for example `real-time-analytics / level-2 / module-4`.
- To analyze candidate locations without generating visuals, explicitly change the scope to “Return only the visual placement plan; do not modify files.”
- If the placement plan is already approved, provide the learning objective and component relationships for each image and begin directly with generation.
