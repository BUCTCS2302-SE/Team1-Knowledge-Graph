#### 1. 环境初始化与约束设置

在数据导入前，必须为核心标识符建立唯一性约束。这能防止节点重复，并显著提升 `MATCH` 操作的性能。

```
// 建立唯一约束
CREATE CONSTRAINT artifact_id_unique FOR (a:Artifact) REQUIRE a.object_id IS UNIQUE;
CREATE CONSTRAINT museum_id_unique FOR (m:Museum) REQUIRE m.id IS UNIQUE;
CREATE CONSTRAINT dynasty_id_unique FOR (d:Dynasty) REQUIRE d.id IS UNIQUE;
CREATE CONSTRAINT artist_id_unique FOR (art:Artist) REQUIRE art.id IS UNIQUE;
```



#### 2. 文物基本信息导入

从 `artifacts.csv` 中导入文物主体节点。

```
:auto
CALL {
  LOAD CSV WITH HEADERS FROM 'file:///artifacts.csv' AS row
  MERGE (a:Artifact {object_id: row.object_id})
  ON CREATE SET 
    a.title_zh = row.title_zh,
    a.title_en = row.title_en,
    a.material = row.material,
    a.type = row.type,
    a.image_url = row.image_url
  ON MATCH SET 
    a.title_zh = row.title_zh,
    a.image_url = row.image_url
} IN TRANSACTIONS OF 2000 ROWS;
```



#### 3. 建立“收藏”关系 (Artifact -> Museum)

将文物与所属博物馆进行关联。

```
:auto
CALL {
  LOAD CSV WITH HEADERS FROM 'file:///artifacts.csv' AS row
  MATCH (a:Artifact {object_id: row.object_id})
  MERGE (m:Museum {id: toInteger(row.museum_id)})
  ON CREATE SET m.name = row.museum_name
  MERGE (a)-[r:COLLECTED_BY]->(m)
} IN TRANSACTIONS OF 1000 ROWS;
```



#### 4. 建立“年代”关系 (Artifact -> Dynasty)

将文物关联至对应的历史朝代。

```
:auto
CALL {
  LOAD CSV WITH HEADERS FROM 'file:///artifacts.csv' AS row
  WITH row WHERE row.dynasty_id IS NOT NULL
  MATCH (a:Artifact {object_id: row.object_id})
  MERGE (d:Dynasty {id: toInteger(row.dynasty_id)})
  ON CREATE SET d.name_zh = row.dynasty_name
  MERGE (a)-[r:BELONGS_TO]->(d)
} IN TRANSACTIONS OF 1000 ROWS;
```



#### 5. 建立“作者”关系 (Artifact -> Artist)

根据关联表数据，建立文物与艺术家的创作关系。

```
:auto
CALL {
  LOAD CSV WITH HEADERS FROM 'file:///artifact_artist_relation.csv' AS row
  MATCH (a:Artifact {object_id: row.object_id})
  MERGE (art:Artist {id: toInteger(row.artist_id)})
  ON CREATE SET art.name_zh = row.artist_name
  MERGE (a)-[r:CREATED_BY]->(art)
  SET r.role = row.relationship_type
} IN TRANSACTIONS OF 1000 ROWS;
```



#### 6. 导入验证查询

执行以下 Cypher 语句，验证三位一体（文物-博物馆-年代-作者）关系网是否构建成功：

```
// 随机预览 200 组关联关系
MATCH (m:Museum)<-[r1:COLLECTED_BY]-(a:Artifact)-[r2:BELONGS_TO]->(d:Dynasty)
OPTIONAL MATCH (a)-[r3:CREATED_BY]->(art:Artist)
RETURN m, r1, a, r2, d, r3, art 
LIMIT 200
```