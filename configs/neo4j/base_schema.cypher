// Base knowledge graph schema for AFR-41
// Nodes: Project, Person, Concept, Document, Problem, Lesson
// Relations: WORKS_ON, RELATES_TO, CAUSED_BY, SOLVED_BY, LEARNED_FROM

// Uniqueness constraints for entity names
CREATE CONSTRAINT project_name_unique IF NOT EXISTS
FOR (n:Project) REQUIRE n.name IS UNIQUE;

CREATE CONSTRAINT person_name_unique IF NOT EXISTS
FOR (n:Person) REQUIRE n.name IS UNIQUE;

CREATE CONSTRAINT concept_name_unique IF NOT EXISTS
FOR (n:Concept) REQUIRE n.name IS UNIQUE;

CREATE CONSTRAINT document_name_unique IF NOT EXISTS
FOR (n:Document) REQUIRE n.name IS UNIQUE;

CREATE CONSTRAINT problem_name_unique IF NOT EXISTS
FOR (n:Problem) REQUIRE n.name IS UNIQUE;

CREATE CONSTRAINT lesson_name_unique IF NOT EXISTS
FOR (n:Lesson) REQUIRE n.name IS UNIQUE;

// Lookup indexes for fast type-filtered queries
CREATE INDEX project_name_index IF NOT EXISTS
FOR (n:Project) ON (n.name);

CREATE INDEX person_name_index IF NOT EXISTS
FOR (n:Person) ON (n.name);

CREATE INDEX concept_name_index IF NOT EXISTS
FOR (n:Concept) ON (n.name);

CREATE INDEX document_name_index IF NOT EXISTS
FOR (n:Document) ON (n.name);

CREATE INDEX problem_name_index IF NOT EXISTS
FOR (n:Problem) ON (n.name);

CREATE INDEX lesson_name_index IF NOT EXISTS
FOR (n:Lesson) ON (n.name);

// Full-text index for cross-entity search
CREATE FULLTEXT INDEX entity_search IF NOT EXISTS
FOR (n:Project|Person|Concept|Document|Problem|Lesson)
ON EACH [n.name, n.description];

// Seed relationship type examples (MERGE avoids duplicates)
MERGE (alice:Person {name: 'Example Person'})
MERGE (proj:Project {name: 'Example Project'})
MERGE (concept:Concept {name: 'Example Concept'})
MERGE (doc:Document {name: 'Example Document'})
MERGE (problem:Problem {name: 'Example Problem'})
MERGE (lesson:Lesson {name: 'Example Lesson'})
MERGE (alice)-[:WORKS_ON]->(proj)
MERGE (proj)-[:RELATES_TO]->(concept)
MERGE (problem)-[:CAUSED_BY]->(concept)
MERGE (problem)-[:SOLVED_BY]->(alice)
MERGE (lesson)-[:LEARNED_FROM]->(problem)
MERGE (doc)-[:RELATES_TO]->(proj);
