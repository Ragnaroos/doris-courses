# Level 2 quiz alignment and review

The existing courses are complete. The questions below were checked against those courses and current Labs. `Review` marks concepts that require course/documentation support beyond what the Lab directly demonstrates; recheck them if the course is revised. No question requires running a Lab.

| Question | Objective | Course section | Lab section / evidence boundary | Review |
|---|---|---|---|---|
| m4_q1 | Keep a consistent grain | 4.1; 4.6 | 1; 5 | Aligned |
| m4_q2 | Interpret Duplicate Key columns | 4.2 | 4 | Aligned |
| m4_q3 | Represent money and identifiers | 4.3; 4.4 | 2; 3 | Aligned |
| m4_q4 | Distinguish omission from NULL | 4.4 | 3 | Aligned |
| m4_q5 | Design for lifecycle and workload | 4.5 | 4 | Course + official docs |
| m4_q6 | Combine additive summary batches | 4.2; 4.6 | 5: single pre-grouped batch only | Course + official docs |
| m5_q1 | Choose by result shape | 5.1 | 1 | Aligned |
| m5_q2 | Filter rows before groups | 5.3; 5.4 | 3; 4 | Aligned |
| m5_q3 | Preserve rows with a window | 5.6 | 6; 7 | Aligned |
| m5_q4 | Give representative values a meaning | 5.4 | 5 | Aligned |
| m5_q5 | Reason about analytical stages | 5.5; 5.6 | 6; 7: no missing-date gap demonstration | Course + official docs |
| m5_q6 | Choose the scope of reusable logic | 5.7 | 8; 10: Java template is not executed | Course + official docs |
| m6_q1 | Return only missing relationships | 6.2 | 2 | Aligned |
| m6_q2 | Predict metric multiplication | 6.1 | 4 | Aligned |
| m6_q3 | Define NULL matching deliberately | 6.3 | 5 | Aligned |
| m6_q4 | Separate hash keys from residual conditions | 6.5 | 6: separate equality and pure inequality plans | Course + official docs |
| m6_q5 | Read planned data movement | 6.6 | 7 | Course + official docs |
| m6_q6 | Interpret a Runtime Filter plan | 6.7 | 7 | Course + official docs |
| m7_q1 | Choose a predicate correction | 7.1; 7.4 | 3 | Aligned |
| m7_q2 | Order states by the source sequence | 7.2 | 1 | Aligned |
| m7_q3 | Predict omitted value columns | 7.3 | 2 | Aligned |
| m7_q4 | Match deletion to its source | 7.5 | 4 | Aligned |
| m7_q5 | Replace a complete Partition | 7.6 | 5: before/after results only | Course + official docs |
| m7_q6 | Separate visibility from cleanup | 7.7 | 4: visibility and metadata, not physical reclamation | Course + official docs |

## Official review sources

- [Aggregate Key](https://doris.apache.org/docs/4.x/table-design/data-model/aggregate/)
- [Alias Function](https://doris.apache.org/docs/4.x/query-data/udf/alias-function/)
- [Joins](https://doris.apache.org/docs/4.x/query-data/join/)
- [Partial column update](https://doris.apache.org/docs/4.x/data-operate/update/partial-column-update/)
- [INSERT OVERWRITE](https://doris.apache.org/docs/4.x/sql-manual/sql-statements/data-modification/DML/INSERT-OVERWRITE/)

The course source lists additionally cover types, defaults, windows, CTEs, ANY_VALUE, Runtime Filters, Sequence columns and MoW. The quizzes target the course Doris 4.x semantics; they do not execute SQL or claim fresh Doris 4.1.3 runtime validation. Complex types, ASOF JOIN, and new-key partial-update policies are deliberately outside this 24-question sample.

## Verification

- All four YAML files load through `CourseQuiz.from_yaml`; each has six unique question IDs and valid answer IDs.
- Notebook schema validation and initialization passed from the course root and each module directory. Delivered notebooks contain no execution output.
- Shared state regression checks cover all seven quizzes: no selection, wrong answer feedback, answer revision, previous/next navigation, scoring, completion-page return and restart. A separate check covers draft preservation.
- In local JupyterLab, all four new quizzes were rendered and navigated from Question 1 through Question 6. Completion was also opened in the browser; completion/revision state is covered for every quiz by regression checks.
- At 480px quiz width, all four final questions had wrapping options (two or three lines). Measured line height was 18.85px; each radio center remained 9.421875px below the label top, at the first-line center, with a left offset of zero. Desktop navigation buttons shared the same baseline; narrow controls wrap without overlapping options.
- Browser inspection used the shared widget in a temporary combined Notebook. VS Code's own renderer was not separately exercised; module-directory initialization was tested.
- Run regression checks with `.venv/bin/python -m unittest discover -s tests -p 'test_quiz.py'`.
