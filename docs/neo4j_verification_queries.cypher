// AFR-42 verification queries for NER + graph builder pipeline

// 1) Node counts by label (Project, Person, Concept, Problem, Lesson, Document)
MATCH (n)
UNWIND labels(n) AS label
RETURN label, count(*) AS count
ORDER BY count DESC;

// 2) Relationship counts by type
MATCH ()-[r]->()
RETURN type(r) AS relationship_type, count(*) AS count
ORDER BY count DESC;

// 3) Documents and entity extraction coverage
MATCH (d:Document)
OPTIONAL MATCH (d)-[:MENTIONS]->(e)
RETURN d.name AS document_id, d.title AS title, count(e) AS mentioned_entities
ORDER BY document_id;

// 4) People and the projects they work on
MATCH (p:Person)-[r:WORKS_ON]->(proj:Project)
RETURN p.name AS person, proj.name AS project, r.method AS extraction_method, r.confidence AS confidence
ORDER BY person, project;

// 5) Problems and their solution paths
MATCH (prob:Problem)-[r:SOLVED_BY]->(solver)
RETURN prob.name AS problem, solver.name AS solved_by, labels(solver)[0] AS solver_type, r.confidence AS confidence
ORDER BY problem;

// 6) Lessons connected to project/problem sources
MATCH (lesson:Lesson)-[r:LEARNED_FROM]->(source)
RETURN lesson.name AS lesson, source.name AS source, labels(source)[0] AS source_type, r.confidence AS confidence
ORDER BY lesson;
