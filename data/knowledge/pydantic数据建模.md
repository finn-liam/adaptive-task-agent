# Pydantic 数据建模与类型契约

Pydantic 的 BaseModel：只需要声明"有哪些字段、什么类型"，就免费获得三样东西——
构造时自动校验（类型不对当场抛 ValidationError）、JSON 序列化/反序列化、
给 LLM 结构化输出当模板。项目中所有节点之间流动的数据都由它把守。

字段声明语法：`字段名: 类型 = 默认值`。没有等号的是必填项；
`str | None = None` 是高频惯用式，意思是"这个字段可有可无，没有的时候就是空"。
范围约束用 Field：`priority: int = Field(default=3, ge=1, le=5)`。

Literal 是白名单类型：`ToolName = Literal["search_web", "fetch_url", ...]`
声明字段的值只能是名单里的字符串。LLM 会幻觉出不存在的工具名，
Literal 就是防幻觉的第一道闸门——ValidationError 报错会列出全部合法值，
把报错原文喂回给 LLM 它就能自己改对。

TypedDict 和 BaseModel 的分工：Pydantic 管数据对象的校验（运行时执法），
TypedDict 只管函数签名层面的字典形状说明（无运行时开销）。
关键区别：TypedDict 没有默认值、不执法——状态图里读未写过的格子会 KeyError，
所以初始状态必须把所有格子铺满。

get_args(ToolName) 能从 Literal 反推出纯字符串元组，让白名单定义一次、处处复用。
