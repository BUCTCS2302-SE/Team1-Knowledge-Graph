# 中国文物数据采集与知识图谱系统

## 技术方案

- 数据爬取：Python
- 数据处理：pandas、csv、chardet
- 爬虫工具：requests、bs4、playwright
- 翻译：百度翻译 API
- 图数据库操作：py2neo
- 数据库：MySQL + Neo4j

## 核心功能

- 海外博物馆中国文物数据爬取及整合
- 数据清洗、去重与标准化
- 中英文字段翻译
- 知识图谱制作及展示

## 数据来源

| 博物馆        | 英文名                               | 数据量      |
| ---------- | --------------------------------- | -------- |
| 旧金山亚洲艺术博物馆 | Asian Art Museum of San Francisco | \~5500 件 |
| 大都会艺术博物馆   | The Metropolitan Museum of Art    | \~4600 件 |
| 费城艺术博物馆    | Philadelphia Museum of Art        | \~2500 件 |

## 目录结构

```
├── spider/                         # 爬虫模块
│   ├── Asian Art Museum of San Francisco/   # Playwright 浏览器自动化爬取
│   ├── daduhui/                             # 大都会博物馆公开 API 爬取
│   └── philamuseum/                         # 费城博物馆搜索 API 并发爬取
├── clean/                          # 数据清洗模块
│   ├── Asian Art Museum of San Francisco/   # 去重、字段校验、朝代匹配
│   ├── daduhui/                             # 空值填充、标准化、去重
│   └── philamuseum/                         
├── translate/                      # 翻译模块（百度翻译 API）
│   ├── Asian Art Museum of San Francisco/
│   ├── daduhui/
│   └── philamuseum/
├── database/                       # MySQL 数据库上传
│   ├── Sql-create(1).md           # 完整建表 SQL
│   ├── Asian Art Museum of San Francisco/
│   ├── daduhui/
│   └── philamuseum/
└── neo4j/                          # Neo4j 图数据库
    ├── Import_neo4j(1).md         # Cypher 导入脚本
    ├── Asian Art Museum of San Francisco/
    └── philamuseum & daduhui/
```

## 实现过程

### 1. 数据爬取

分别针对三家博物馆网站编写爬虫脚本：

- **旧金山亚洲艺术博物馆**：使用 Playwright 浏览器自动化，分页抓取藏品列表并进入详情页提取字段，支持断点续爬
- **大都会艺术博物馆**：调用公开 API（`collectionapi.metmuseum.org`）搜索文物 ID 并逐个获取详情，增量保存
- **费城艺术博物馆**：通过搜索 API 分页查询，多线程并发获取详情页，支持失败重试和去重

采集字段包括：标题、图片 URL、藏品编号、艺术家、年代、材质、尺寸、来源、文化等。

### 2. 数据清洗

博物馆数据爬取完毕后，数据文件以 UTF-8 格式导出 CSV，之后进行筛选以及清洗：

- 去除完全重复行和无图片记录
- 关键字段完整性校验（如 Date 须数字开头）
- 朝代 ID 匹配（从朝代表映射或年份推算）
- 空值填充与字符串标准化（小写+去空格）

### 3. 数据翻译

编写代码，调用百度翻译等 API 接口，进行数据的翻译：

- 翻译字段：标题、材质、类型、描述、艺术家名称
- 支持批量翻译、断点续传、余额不足中断保护
- 对翻译不合适的地方进行手动翻译修正

### 4. MySQL 数据库存储

将清洗翻译后的数据上传至 MySQL 数据库 `seitem`，核心表包括：

- museums（博物馆）
- dynasties（朝代）
- artists（艺术家）
- artifacts（文物）
- artifact\_images（文物图片）
- artifact\_artist（文物-艺术家关联）

详细建表 SQL 见 [Sql-create.md](database/Sql-create\(1\).md)

### 5. 知识图谱制作及展示

设计三元组并建模，因为文物有重名，因此三元组内一致采用文物 ID 作为主键。

三元组建模完成后，将三元组文件放入服务器上的 Neo4j 的 import 文件夹中。

节点类型：

- Museum（博物馆）
- Artifact（文物）
- Period（朝代）
- Artist（艺术家）

关系类型：

- 包含（Museum → Artifact）
- 年代（Artifact → Period）
- 作者（Artifact → Artist）

连接 Neo4j：`http://123.56.94.39:7474/`

账户：neo4j

执行以下语句即可在知识图谱中展现出所有关系：

```cypher
MATCH (m:Museum)-[r1:包含]->(a:Artifact)
MATCH (a)-[r2:年代]->(p:Period)
MATCH (a)-[r3:作者]->(artist:Artist)
RETURN m, r1, a, r2, p, r3, artist SKIP 1000 LIMIT 1000
```

因为服务器以及 Neo4j 性能的限制，一次只能展现出一千条左右，可通过修改 `SKIP` 和 `LIMIT` 参数分页浏览。

Neo4j 导入脚本详见 [Import\_neo4j.md](neo4j/Import_neo4j\(1\).md)
