import argparse
import hashlib
import json
import os
import re
from datetime import datetime
from pathlib import Path
from urllib.request import Request, urlopen


BASE_DIR = Path(__file__).resolve().parent
DATA_DIR = BASE_DIR / "data"
REPORTS_DIR = BASE_DIR / "reports"
NEWS_DETAILS_DIR = REPORTS_DIR / "news_details"
LLM_DIGEST_CACHE = {}
LLM_DIGEST_DISABLED_REASON = None
LOCAL_ENV_FILES = [
    BASE_DIR / ".env.local",
    BASE_DIR / ".env",
    BASE_DIR / "config" / ".env",
]

GRADE_TITLES = {
    "confirmed_event": "今日重大事件 confirmed_event",
    "recent_signal": "近期重要变化 recent_signal",
    "watch_signal": "名单外新增信号 watch_signal",
    "background_ref": "背景参考 background_ref",
    "failed_source": "风险信号与信息盲区 failed_source",
}

LAYER_NAMES = {
    "energy": "energy 能源层",
    "chips": "chips 芯片 / 计算层",
    "infrastructure": "infrastructure 基础设施层",
    "models": "models 模型层",
    "applications": "applications 应用层",
    "capital": "capital 资本层",
}

PURPOSE_NAMES = {
    "api_change": "API 变化",
    "application_signal": "应用信号",
    "azure_openai_update": "Azure OpenAI 更新",
    "chatgpt_apps_update": "ChatGPT 应用更新",
    "chip_update": "芯片 / 算力更新",
    "chip_equipment_update": "半导体设备更新",
    "cloud_ai_update": "云 AI 更新",
    "cloud_infra_update": "云基础设施更新",
    "cloud_update": "云平台更新",
    "coding_agent_update": "编程 Agent 更新",
    "developer_signal": "开发者生态信号",
    "energy_signal": "能源信号",
    "model_product_update": "模型 / 产品更新",
    "model_research_update": "模型研究更新",
    "model_update": "模型更新",
    "reference": "背景参考",
}

TYPE_NAMES = {
    "aggregator": "聚合页",
    "benchmark": "基准测试",
    "blog": "博客",
    "changelog": "变更日志",
    "discovery": "发现源",
    "github_release": "GitHub 发布",
    "ir": "投资者关系",
    "newsroom": "新闻稿",
    "release_notes": "发布说明",
    "rss": "RSS",
    "web": "网页",
}

TITLE_TRANSLATIONS = [
    ("fable 5 and mythos 5", "Anthropic 因美国政府指令暂停 Fable 5 和 Mythos 5 访问"),
    ("introducing claude corps", "Anthropic 推出 Claude Corps 公益与人才项目"),
    ("public record", "Anthropic 发布首期 Public Record 公众态度调查结果"),
    ("compliance api", "Claude Compliance API 企业合规集成更新"),
    ("claude design", "Claude Design 研究预览更新"),
    ("role-based", "Claude Enterprise 角色权限能力更新"),
    ("agentic coding performance", "NVIDIA 发布 Agentic Coding 基准表现更新"),
    ("minimax m3", "NVIDIA 发布 MiniMax M3 长上下文部署方案"),
    ("apigee hybrid", "Google Cloud Apigee hybrid 升级与文档更新"),
    ("diffusiongemma", "Google 发布 DiffusionGemma 开发者指南"),
    ("google colab cli", "Google 发布 Colab CLI 开发者工具"),
    ("gemma 4 12b", "Google 发布 Gemma 4 12B 开发者指南"),
    ("amd commits", "AMD 宣布在英国投入最高 20 亿英镑推进 AI 创新"),
    ("github", "GitHub 开发者生态观察信号"),
    ("hugging face", "Hugging Face Spaces 应用观察信号"),
    ("artificial analysis", "Artificial Analysis 模型与 Agent 基准观察信号"),
    ("lmarena", "LMArena 模型榜单观察信号"),
    ("techcrunch", "TechCrunch AI 新闻观察信号"),
]

TITLE_BY_KEYWORD = [
    ("sk hynix and nvidia announce multi-year", "SK Hynix 与 NVIDIA 建立多年技术合作推进 AI 工厂内存"),
    ("bugbot is now over 3x faster", "Cursor Bugbot 审查速度提升 3 倍、成本下降 22%"),
    ("cohere.com/products", "Cohere 展示企业 AI 产品矩阵：North、Compass、Command、Transcribe 和 Embed"),
    ("cohere.com/\nenterprise ai", "Cohere 强调企业私有化部署和可控 AI 基础设施"),
    ("cohere.com/blog/tag/research", "Cohere 研究线聚焦工作未来、多语言模型和企业可信 AI"),
    ("frontier-model-defense", "Cloudflare 以自身架构演示如何防御前沿网络攻击模型"),
    ("announcing-neural-dawn", "Arm 发布 Neural Dawn 展示移动端 AI 图形和神经渲染能力"),
    ("ai-model-cards-environmental-metrics", "Salesforce 将能耗和碳排放指标纳入 AI Model Cards"),
    ("readiness-architects-slackbot", "Salesforce 用 Slackbot 展示 Agentic Enterprise 内部知识工作流"),
    ("adobe reports record q2 results", "Adobe 公布创纪录 Q2 业绩并强调企业 AI 渗透"),
    ("openai api changelog", "OpenAI API Changelog 背景页：需继续跟踪具体 API 变更"),
    ("openai apps sdk changelog", "OpenAI Apps SDK Changelog 背景页：需继续跟踪具体应用生态变更"),
    ("frontier ai llms", "Mistral 官网信号：前沿模型、助手、Agent 和企业服务"),
    ("blog | coreweave", "CoreWeave 博客页信号：AI 云基础设施持续扩展"),
    ("broadcom | newsroom", "Broadcom 新闻页信号：AI 网络和定制芯片链需继续跟踪"),
    ("newsroom | palantir", "Palantir 新闻页信号：AIP 企业和政府落地需继续跟踪"),
]

SUMMARY_TRANSLATIONS = [
    (
        "fable 5 and mythos 5",
        "Anthropic 表示，美国政府基于国家安全权限发出出口控制指令，要求暂停任何外国国民访问 Fable 5 和 Mythos 5，范围包括美国境内外的外国国民以及 Anthropic 自身外籍员工；其他 Anthropic 模型暂不受影响。公司称其在 5:21pm ET 收到政府指令，信中没有给出完整国家安全细节，Anthropic 目前理解为政府关注 Fable 5 存在某种 jailbreak 绕过方法。Anthropic 还表示，其看到的演示主要用于识别少量已知、轻微漏洞，并认为其他公开模型也可能存在类似问题。投资上看，这不是单纯产品下线，而是高能力模型被直接纳入出口控制和国家安全治理的案例，会影响企业客户对模型可用性、跨境团队权限、服务连续性和合规审计的评估。",
    ),
    (
        "introducing claude corps",
        "Anthropic 推出 Claude Corps，定位为全国性 fellowship 项目，面向职业早期、希望把 AI 用于社区服务的人群。公司计划培训 1,000 名 fellows 深度使用 Claude，并把他们匹配到美国各地非营利组织，全职、线下工作一年，帮助这些组织把 Claude 用到日常任务、系统建设和使命推进中。Anthropic 承诺初始投入 1.5 亿美元，并把该项目描述为在重大经济变化期扩大 AI 收益的一种模式。投资上看，这不是直接收入事件，但它有三层意义：一是扩大 Claude 在真实组织工作流中的使用案例；二是培养熟悉 Claude 的人才网络；三是缓解公众对 AI 冲击就业和社会分配的担忧，增强 Anthropic 的政策与品牌缓冲。",
    ),
    (
        "public record",
        "Anthropic 发布首期 Public Record 调查结果，样本接近 52,000 名美国人，调查时间为 2025 年 11 月至 12 月。结果显示，公众对 AI 的最大期待集中在治疗癌症、阿尔茨海默病等疾病，帮助残障人士，以及推动技术进步和让生活更便利；但担忧也非常集中，AI 导致工作流失是各州最普遍的恐惧，其次是认知依赖和虚假信息。超过 70% 的受访者认为政府应在 AI 监管中发挥作用，且这种支持具有跨党派特征。投资上看，这类调查不是产品发布，但它揭示了模型公司未来商业化的社会约束：就业、隐私、儿童安全、责任归属和监管透明度会持续影响企业采购、政策风险和产品设计。",
    ),
    (
        "compliance api",
        "Claude Compliance API 面向 Claude Enterprise 和 Claude Platform 客户，允许企业安全与合规平台接入 Claude 使用数据，帮助组织在既有工具中监控 Claude 活动。文档显示，相关集成覆盖 DLP、SASE、数据安全、SIEM、安全运营、身份、eDiscovery、AI 安全态势管理、AI 可观测性和遥测基础设施等类别；可访问的数据包括 Claude Enterprise 的会话内容、上传文件、项目、用户登录、管理员操作和组织设置变更等活动信息。投资上看，这说明 Anthropic 正在把企业 AI 的竞争点从模型能力延伸到治理和审计能力。对大型企业而言，能否接入现有安全栈、满足合规要求，往往决定 AI 工具能否从小范围试点进入全员部署。",
    ),
    (
        "claude design",
        "Claude Design by Anthropic Labs 支持用户通过对话创建设计、交互原型、演示文稿等内容，界面由左侧聊天和右侧画布组成，用户可以通过对话和内联评论持续迭代。文档强调，该能力可以结合组织设计系统，自动使用企业的颜色、字体和组件模式，面向 Pro、Max、Team 和 Enterprise 计划开放研究预览，企业计划默认关闭。投资上看，这代表 Anthropic 正从通用聊天、代码和文本工作流进入可视化设计与原型制作场景，潜在竞争边界会触及 Figma、Canva、Adobe 以及办公套件中的生成式设计能力。由于仍是 research preview，短期应重点观察可用性、导出能力、团队协作和付费转化。",
    ),
    (
        "role-based",
        "Claude Enterprise 文档显示，企业计划支持 role-based permissions，组织可以按团队或成员组控制不同功能、连接器和管理权限，也可以委派账单、用户管理、身份与访问等特定管理员能力，而不必给所有管理员相同权限。该功能要求组织先理解 groups、spend limits 和 custom roles，并在组织设置中确认功能开关。投资上看，细粒度权限是企业 AI 从个人和小团队使用走向大型组织部署的基础条件。它降低了合规、数据访问和内部治理阻力，也有助于 Anthropic 把 Claude Enterprise 做成可管理、可审计、可分级授权的平台产品。",
    ),
    (
        "agentic coding performance",
        "NVIDIA 称 Artificial Analysis AA-AgentPerf 是首个面向真实 coding trajectories 的开放、多厂商 agentic inference benchmark，重点衡量并发 AI agent 在真实编码任务中的吞吐表现，并把结果按 accelerator 和每兆瓦进行归一化。NVIDIA 表示，GB300 NVL72 在该基准中相较 H200 实现最高 20 倍的每兆瓦并发 agent 吞吐提升，背后利用 WideEP/DeepEP、DeepGEMM、fused MoE、NVLink scale-up 等优化；文章还提到未来 Vera Rubin 平台会进一步提升 NVFP4 compute。投资上看，这说明 AI 基础设施评估正在从单次请求延迟、tokens/s，转向 agent 并发、工具调用延迟、序列长度波动和每瓦吞吐。若云厂商和企业按这种负载采购算力，NVIDIA 的 Blackwell/GB300 平台经济性叙事会更强。",
    ),
    (
        "minimax m3",
        "NVIDIA 介绍 MiniMax M3 在其加速基础设施上的部署方案。MiniMax M3 是 428B 参数 Mixture-of-Experts 模型，支持 1M token 上下文和原生多模态，覆盖文本、视觉和代码任务，面向长上下文推理与 agentic workflow。文章强调 MiniMax Sparse Attention 通过预过滤阶段降低标准注意力的二次复杂度影响，在 1M context 下提升 KV cache 访问效率并降低 per-token compute 成本；部署侧则可结合 TensorRT LLM、SGLang、vLLM 和 NVIDIA Dynamo。投资上看，这不是单个模型新闻，而是 NVIDIA 把长上下文、多模态、推理框架和 Blackwell 基础设施打包成平台方案，强化其从硬件到推理软件栈的生态控制力。",
    ),
    (
        "apigee hybrid",
        "Google Cloud 更新 Apigee hybrid v1.16 相关文档，内容覆盖混合云 API 管理平台的 Google Cloud 项目与组织配置、runtime 安装、环境和环境组设置，以及从 v1.15.x 或 v1.16.x 升级到 v1.16.5 的流程。该条本身不是明确 AI 产品发布，更偏企业 API 管理基础设施维护；但在 AI 应用进入企业系统后，API gateway、流量治理、身份认证、版本管理和混合云部署会成为企业 AI 落地的底层能力。投资上看，它对 Google Cloud 的 AI 直接拉动较弱，适合作为基础设施连续迭代信号，而不是强投资事件。",
    ),
    (
        "diffusiongemma",
        "Google 发布 DiffusionGemma 开发者指南。DiffusionGemma 基于 Gemma 4 架构，采用 diffusion-based parallel generation，目标是通过并行生成绕开传统自回归生成中的部分内存带宽瓶颈。该路线值得关注，因为它可能影响本地和云端文本生成的速度、成本和模型服务方式。",
    ),
    (
        "google colab cli",
        "Google 发布 Colab CLI，使开发者和 AI Agent 可以从本地终端连接远程 Colab runtime，请求 GPU/TPU、远程执行脚本、下载产物和查看日志。该工具把云端算力包装成 agent 可直接调用的命令行资源，可能提高 Colab 在开发者和自动化工作流中的使用频率。",
    ),
    (
        "cohere.com/products",
        "Cohere 产品页显示其企业 AI 平台围绕 North、Compass、Command、Transcribe、Embed 等能力展开，重点是把模型、企业搜索、文档生成、语音转写和数据工作流集成到安全可控的企业环境中。页面强调可与企业系统、数据和工作流从部署第一天开始集成，并支持安全、可扩展的生产环境。投资上看，Cohere 的定位不是消费级通用助手，而是企业私有化、可控部署和业务数据结合的模型平台，核心观察点应是大客户采用、私有云/on-prem 部署、RAG/搜索场景和企业合同转化。",
    ),
    (
        "cohere.com/\nenterprise ai",
        "Cohere 官网首页强调“Own your AI”，主线是让企业在自己的数据和基础设施上部署 AI。页面突出安全、灵活、独立三个卖点，包括 VPC、on-premises、专属 Cohere-managed Model Vault，以及基于企业私有数据训练和定制模型。其 North 工作空间、Command 模型、Transcribe 和 Embed 等产品共同指向企业级 agent、搜索、语音和知识工作流。投资上看，Cohere 更像企业 AI 基础供应商，关键不是短期爆款应用，而是能否在金融、公共部门、能源、医疗、制造、通信等行业形成可复制的生产部署。",
    ),
    (
        "cohere.com/blog/tag/research",
        "Cohere Research 页面显示其近期研究主题包括工作未来、研究过程可视化、语音识别、Tiny Aya、多语言模型和模型评测等。最新条目“The future of work debate has an evidence problem”发布于 2026-06-10，说明 Cohere 仍在围绕企业 AI 影响、开放研究和多语言能力建设技术叙事。投资上看，这类研究信号本身不等同于收入，但能帮助判断 Cohere 在企业可信 AI、多语言模型和开发者生态上的长期技术储备。",
    ),
    (
        "bugbot is now over 3x faster",
        "Cursor Changelog 显示 Bugbot 性能显著提升：平均代码审查时间从约 5 分钟降至约 90 秒，单次审查发现的 bug 数平均提高 10%，每次运行成本下降约 22%。这些改进来自 Composer 2.5，并且 Bugbot 现在支持在 push 前通过 /review、/review-bugbot 和 /review-security 运行，也能与 GitHub / GitLab PR 流程同步。投资上看，AI 编程工具正在从“写代码”扩展到“审代码、安全检查、CI 前质量控制”，这会提高企业开发流程嵌入深度和付费黏性。",
    ),
    (
        "frontier-model-defense",
        "Cloudflare AI Blog 讨论如何防御 frontier cyber models 带来的网络安全风险。文章基于 Cloudflare 自身作为 customer zero 的安全架构，强调当模型能更快发现漏洞、推理攻击链并生成可运行 proof 时，企业不能只依赖补丁速度，而要关注架构层面的隔离、监控、WAF、Zero Trust、Cloudforce One、Bot Management 等防线。投资上看，AI 提升攻防效率会推动安全基础设施升级，利好具备网络边缘、安全和流量治理能力的平台型厂商。",
    ),
    (
        "announcing-neural-dawn",
        "Arm 发布 Neural Dawn，展示 Arm Neural Technology 与 Unreal Engine MegaLights 在移动端游戏中的应用。该项目由 Arm 和 Sumo Digital 开发，面向下一代 Arm Mali GPU，目标是在移动设备上实现更接近桌面级的动态光照和沉浸式视觉效果，同时保持电池寿命。投资上看，这条信号更偏 edge AI 和终端图形能力，说明 AI 加速和神经渲染不仅用于云端大模型，也在进入移动 GPU、游戏和设备端体验。",
    ),
    (
        "ai-model-cards-environmental-metrics",
        "Salesforce 扩展 AI model cards，加入标准化环境影响指标，帮助客户理解 AI 模型生命周期中的能耗和碳排放。Salesforce 表示，随着 AI 采用加速，客户不只关心模型性能，也希望看到模型构建和运行方式的环境透明度。投资上看，企业 AI 采购会越来越关注治理、合规、可持续性和透明度；这类能力可能成为大型 SaaS 厂商在企业市场中降低采购阻力的差异化因素。",
    ),
    (
        "adobe newsroom",
        "Adobe Newsroom 首页显示 Adobe 于 2026-06-11 发布创纪录 Q2 业绩，并强调财富 100 强中 99% 使用 Adobe AI 转型工作方式、Adobe Experience Platform 每年支撑超过 1 万亿次全球体验、全球有 20,000 家企业客户。该条偏资本和应用层交叉信号，说明生成式 AI 正被 Adobe 嵌入创意、营销和体验平台。投资上看，后续应重点跟踪 Firefly、Experience Platform、企业客户 AI 使用量和 AI 对订阅收入/利润率的贡献。",
    ),
    (
        "sk hynix and nvidia announce multi-year",
        "SK Hynix Newsroom 首页显示，SK Hynix 与 NVIDIA 宣布多年技术合作，目标是推进面向 AI factories 的下一代内存技术。页面同时突出 HBM3E、HBM4、CXL、eSSD、DRAM 等 AI memory 主题，并列出 iHBM 散热方案、SOCAMM2 量产、IEEE Corporate Innovation Award 等近期进展。投资上看，这条信号强化了 SK Hynix 在 AI 服务器内存、HBM 供给和 NVIDIA 生态中的战略位置，后续应重点跟踪 HBM4 量产、客户认证、产能扩张和价格趋势。",
    ),
    (
        "readiness-architects-slackbot",
        "Salesforce 通过“Ask a Readiness Architect's Slackbot”展示其 Agentic Enterprise 叙事：Slackbot 可以基于员工真实 Slack 对话、客户实施、研究和相关文档回答工作问题，同时遵守权限和 Salesforce Trust Layer。该案例强调 AI agent 在企业内部知识检索、跨团队沟通、客户准备和组织学习中的作用。投资上看，它不是单独产品发布，而是 Salesforce 把 Slack、Trust Layer 和 agent 工作流包装为企业 AI 使用范式的内容营销信号。",
    ),
    (
        "openai api changelog",
        "OpenAI API Changelog 本次抓取到的是文档级背景页，页面包含 API、Responses、Agents SDK、工具调用、ChatKit、MCP、文件检索、图像生成、代码解释器等导航信息，但没有稳定提取到单条变更的发布时间和正文。该源仍然重要，因为 API 能力、模型调用方式、工具生态和计费/上下文变化会影响开发者平台竞争力。后续应重点跟踪具体变更条目，避免把文档首页当成事件。",
    ),
    (
        "openai apps sdk changelog",
        "OpenAI Apps SDK Changelog 本次抓取到的是文档级背景页，反映 ChatGPT Apps SDK、组件、工具、MCP、Connectors 和 ChatGPT 内应用生态的入口信息，但没有稳定提取到单条发布时间明确的变更。该源适合继续保留在核心监控中，因为 ChatGPT 应用平台变化可能影响应用层生态、开发者分发和企业集成。后续需要跟踪具体 changelog 条目，避免文档导航页进入事件区。",
    ),
    (
        "frontier ai llms",
        "Mistral 官网页面显示其定位覆盖 frontier AI LLMs、assistants、agents 和 services，强调面向企业的模型、助手和服务能力。当前抓取到的是官网级背景页，缺少明确发布日期和单个产品事件，因此不能作为今日重大事件。投资上看，Mistral 仍应作为欧洲前沿模型厂商纳入核心观察，后续需要更精确的 news / release 页面来捕捉模型发布、企业合作和商业化进展。",
    ),
    (
        "blog | coreweave",
        "CoreWeave 博客页抓取到的是博客入口而非具体文章，说明该源已经纳入监控，但还需要提取具体文章标题、日期和正文。作为 AI 云基础设施厂商，CoreWeave 的有效信号应包括 GPU 容量扩张、客户合同、区域数据中心、推理/训练服务更新和资本开支。当前条目只能作为背景覆盖信号，不能形成强投资结论。",
    ),
    (
        "broadcom | newsroom",
        "Broadcom 新闻页抓取到的是 newsroom 入口而非具体新闻。Broadcom 在 AI 网络、交换芯片、定制 ASIC 和数据中心连接中具备重要位置，但本条没有具体发布时间和事件正文。投资上看，该源值得保留，但需要后续解析具体新闻稿，重点关注 AI ASIC 客户、以太网 AI fabric、Tomahawk / Jericho 等数据中心网络产品和相关订单。",
    ),
    (
        "newsroom | palantir",
        "Palantir 新闻页抓取到的是 newsroom 入口，不是具体公告。Palantir AIP 是企业和政府 AI 应用层的重要观察对象，有效信号应包括大型客户合同、AIP bootcamp 转化、政府订单、行业解决方案和财务指引。当前条目只能说明该源已覆盖，不能直接形成今日事件判断。",
    ),
    (
        "gemma 4 12b",
        "Google 发布 Gemma 4 12B 开发者指南。该模型面向本地多模态执行，采用统一、encoder-free 架构，并支持音频输入和消费级设备部署。该信号说明端侧和本地 AI 仍是 Google 在云端 API 之外的重要路线。",
    ),
    (
        "amd commits",
        "AMD 宣布未来五年在英国投入最高 20 亿英镑，支持 advanced computing、科学研究和人才发展，并与 Imperial College London、Oriole Networks 等建立合作。相关项目涉及 AMD Instinct GPU、EPYC CPU 和 ROCm。该事件强化 AMD 在主权 AI 基础设施和科研算力生态中的存在感。",
    ),
    (
        "hugging face",
        "Hugging Face Spaces 页面显示本周热门 AI 应用，包括 Ideogram 4、TripoSplat、Gemma 4 12B IT、Miso TTS 8B、Dots.tts 等。该条属于应用发现信号，需要进一步验证具体使用量、增长速度、模型授权和商业化路径。",
    ),
    (
        "artificial analysis",
        "Artificial Analysis 页面显示其正在跟踪模型能力、速度、价格和 agent benchmark，并出现 AA-AgentPerf、Coding Agent Benchmarks、HyperNova 60B、Gemma 4 12B、Claude Fable 5 等相关更新。该条可用于发现模型和 agent 基准变化，但需要具体分数和横向比较才能形成投资判断。",
    ),
    (
        "claude-code",
        "Claude Code Releases 页面显示 Claude Code 有新版本发布，项目关注度较高。该条属于开发者工具观察信号，需要进一步读取具体 changelog、下载量、企业采用和功能变化。",
    ),
    (
        "techcrunch",
        "TechCrunch AI 频道出现 Anthropic、Meta 等 AI 相关新闻。该条只是新闻聚合入口，不能直接作为投资结论，需要进入具体文章验证发布时间、事实来源和公司影响。",
    ),
    (
        "github.com/trending",
        "GitHub Trending 可用于发现开发者社区正在关注的新项目和工具，但当前抓取只拿到趋势页本身，没有结构化提取具体 repo、star 增速和 AI 相关性。因此该条只能作为后续发现入口。",
    ),
    (
        "lmarena",
        "LMArena 可用于观察模型偏好排名和竞技场表现变化，但当前抓取未提取具体模型、排名、分数和变动幅度。该条需要专项解析后才能用于模型层投资判断。",
    ),
]


def load_local_env_files():
    for path in LOCAL_ENV_FILES:
        if not path.exists():
            continue
        for raw_line in path.read_text(encoding="utf-8").splitlines():
            line = raw_line.strip()
            if not line or line.startswith("#"):
                continue
            if line.startswith("export "):
                line = line[len("export "):].strip()
            if "=" not in line:
                continue
            key, value = line.split("=", 1)
            key = key.strip()
            value = value.strip().strip('"').strip("'")
            if key and key not in os.environ:
                os.environ[key] = value


def env_first(*names, default=""):
    for name in names:
        value = os.getenv(name)
        if value:
            return value.strip()
    return default


def parse_args():
    parser = argparse.ArgumentParser(
        description="Generate a local AI investment daily report from raw_items JSON."
    )
    parser.add_argument(
        "--date",
        default=datetime.now().strftime("%Y-%m-%d"),
        help="Report date in YYYY-MM-DD format. Defaults to today.",
    )
    parser.add_argument(
        "--input",
        default=None,
        help="Raw items JSON path. Defaults to data/raw_items_DATE.json.",
    )
    parser.add_argument(
        "--output",
        default=None,
        help="Markdown report path. Defaults to reports/DATE.md.",
    )
    return parser.parse_args()


def load_payload(path):
    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)

    if isinstance(data, list):
        return {
            "generated_at": None,
            "source_count": None,
            "item_count": len(data),
            "summary": {},
            "items": data,
        }

    return data


def clean_inline(text, max_len=220):
    text = re.sub(r"\s+", " ", text or "").strip()
    if len(text) <= max_len:
        return text
    return text[: max_len - 1].rstrip() + "…"


def markdown_anchor(text):
    cleaned = re.sub(r"[^\w\u4e00-\u9fff-]+", "-", text.lower()).strip("-")
    return cleaned or "section"


def detail_heading(item):
    suffix = hashlib.sha1((item.get("url") or item.get("title") or "").encode("utf-8")).hexdigest()[:8]
    return f"新闻详情 {suffix}：{clean_inline(chinese_event_title(item), 90)}"


def detail_id(item):
    return hashlib.sha1((item.get("url") or item.get("title") or "").encode("utf-8")).hexdigest()[:8]


def detail_link(item, report_date):
    return f"[查看新闻全文中文页](news_details/{report_date}/{detail_id(item)}.html)"


def clean_article_content(content):
    content = re.sub(r"\s+", " ", content or "").strip()
    noise_phrases = [
        "Skip to main content",
        "Skip to footer",
        "Download as PDF",
        "Navigation Menu",
        "Toggle navigation",
        "Sign in",
        "Sign up",
        "Load More",
        "No items found",
    ]
    for phrase in noise_phrases:
        content = content.replace(phrase, " ")
    return re.sub(r"\s+", " ", content).strip()


def article_sentences(item, limit=24):
    content = clean_article_content(item.get("content") or "")
    if not content:
        return []
    chunks = re.split(r"(?<=[.!?。！？])\s+", content)
    sentences = []
    seen = set()
    for chunk in chunks:
        chunk = clean_inline(chunk, 520)
        lower = chunk.lower()
        if len(chunk) < 45:
            continue
        if any(marker in lower for marker in ["cookie", "privacy policy", "all rights reserved", "search docs"]):
            continue
        if lower in seen:
            continue
        seen.add(lower)
        sentences.append(chunk)
        if len(sentences) >= limit:
            break
    return sentences


def sentence_score(sentence, item):
    title_terms = {
        term.lower()
        for term in re.findall(r"[A-Za-z][A-Za-z0-9.+-]{2,}", item.get("title") or "")
        if term.lower() not in {"the", "and", "with", "from", "for"}
    }
    lower = sentence.lower()
    score = sum(2 for term in title_terms if term in lower)
    score += 2 if re.search(r"\d", sentence) else 0
    for keyword in [
        "announce",
        "launch",
        "release",
        "update",
        "customer",
        "enterprise",
        "investment",
        "revenue",
        "performance",
        "model",
        "gpu",
        "cloud",
        "agent",
        "security",
        "compliance",
    ]:
        if keyword in lower:
            score += 1
    return score


TRANSLATION_REPLACEMENTS = [
    (r"\bannounced\b", "宣布"),
    (r"\bannounces\b", "宣布"),
    (r"\blaunch(?:ed|es)?\b", "推出"),
    (r"\breleas(?:ed|es)?\b", "发布"),
    (r"\bintroduc(?:ed|es|ing)?\b", "推出"),
    (r"\bupdate(?:d|s)?\b", "更新"),
    (r"\binvestment\b", "投资"),
    (r"\binvest\b", "投资"),
    (r"\bpartnerships?\b", "合作"),
    (r"\bcustomers?\b", "客户"),
    (r"\benterprises?\b", "企业"),
    (r"\bdevelopers?\b", "开发者"),
    (r"\bmodels?\b", "模型"),
    (r"\bmultimodal\b", "多模态"),
    (r"\breasoning\b", "推理"),
    (r"\bagentic\b", "Agent 化"),
    (r"\bagents?\b", "Agent"),
    (r"\bcloud\b", "云"),
    (r"\bdata centers?\b", "数据中心"),
    (r"\bAI factories\b", "AI 工厂"),
    (r"\bperformance\b", "性能"),
    (r"\bsecurity\b", "安全"),
    (r"\bcompliance\b", "合规"),
    (r"\baccess\b", "访问"),
    (r"\bgovernment\b", "政府"),
    (r"\bnational security\b", "国家安全"),
    (r"\bexport control\b", "出口管制"),
    (r"\brevenue\b", "收入"),
    (r"\bresearch\b", "研究"),
    (r"\bworkforce\b", "劳动力"),
    (r"\bopen source\b", "开源"),
]


def content_based_summary(item, max_sentences=3):
    sentences = article_sentences(item)
    if not sentences:
        return ""
    ranked = sorted(sentences[:12], key=lambda sentence: sentence_score(sentence, item), reverse=True)
    chosen = ranked[:max_sentences]
    return "；".join(clean_inline(sentence, 260).rstrip(".") for sentence in chosen)


def translated_detail_lines(item, max_sentences=10):
    llm_detail = llm_article_digest(item)
    if llm_detail:
        return llm_detail
    local_lines = local_article_detail_lines(item, max_sentences=max_sentences)
    if local_lines:
        return local_lines
    if not has_translation_api():
        return ["未生成 Kimi 译文：当前进程没有读取到 KIMI_API_KEY / MOONSHOT_API_KEY / OPENAI_API_KEY。"]
    return ["Kimi 翻译暂不可用：API 调用失败或返回为空，已无可用正文可供本地整理。"]


def local_article_detail_lines(item, max_sentences=10):
    lines = []
    summary = curated_summary(item)
    if summary:
        lines.append(summary)
    elif item.get("summary"):
        lines.append(clean_inline(item.get("summary"), 520))

    impact = impact_note(item)
    if impact:
        lines.append(f"投资观察：{impact}")
    return lines[:max_sentences]


def has_translation_api():
    return bool(env_first("KIMI_API_KEY", "MOONSHOT_API_KEY", "OPENAI_API_KEY"))


def llm_article_digest(item):
    global LLM_DIGEST_DISABLED_REASON
    if LLM_DIGEST_DISABLED_REASON:
        return []
    if not has_translation_api():
        return []
    cache_key = item.get("url") or item.get("title") or json.dumps(item, sort_keys=True, ensure_ascii=False)
    if cache_key in LLM_DIGEST_CACHE:
        return LLM_DIGEST_CACHE[cache_key]

    content = clean_article_content(item.get("content") or "")
    if not content:
        return []
    prompt = (
        "你是财经新闻翻译和投资情报编辑。请基于下面 URL 抓取正文，输出中文内容，不要编造。"
        "要求：1）先用 3-5 条要点概括新闻事实；2）再用 5-8 条翻译/整理正文关键内容；"
        "3）保留公司名、产品名、模型名、技术名英文；4）不要输出免责声明；5）每条独立成句。\n\n"
        f"标题：{item.get('title') or ''}\n"
        f"来源：{item.get('company') or ''}\n"
        f"URL：{item.get('url') or item.get('source_url') or ''}\n"
        f"正文：{content[:7000]}"
    )
    try:
        text = call_chat_model(prompt)
    except Exception as exc:
        LLM_DIGEST_DISABLED_REASON = f"{type(exc).__name__}: {exc}"
        return []
    lines = [
        clean_inline(re.sub(r"^\s*[-*\d.、]+\s*", "", line), 520)
        for line in text.splitlines()
        if clean_inline(re.sub(r"^\s*[-*\d.、]+\s*", "", line), 520)
    ]
    if not lines and text.strip():
        lines = [clean_inline(part, 520) for part in re.split(r"[。；]\s*", text) if clean_inline(part, 520)]
    LLM_DIGEST_CACHE[cache_key] = lines[:12]
    return LLM_DIGEST_CACHE[cache_key]


def call_chat_model(prompt):
    kimi_key = env_first("KIMI_API_KEY", "MOONSHOT_API_KEY")
    if kimi_key:
        api_key = kimi_key
        base_url = env_first("KIMI_BASE_URL", "MOONSHOT_BASE_URL", "AI_AGENT_BASE_URL", default="https://api.moonshot.cn/v1").rstrip("/")
        model = env_first("KIMI_MODEL", "MOONSHOT_MODEL", "AI_AGENT_MODEL", default="kimi-k2.5")
    else:
        api_key = env_first("OPENAI_API_KEY")
        base_url = env_first("OPENAI_BASE_URL", default="https://api.openai.com/v1").rstrip("/")
        model = env_first("OPENAI_MODEL", default="gpt-5-mini")
    if not api_key:
        return ""

    payload = {
        "model": model,
        "messages": [
            {"role": "system", "content": "你只基于用户提供的正文做中文概括和翻译整理。"},
            {"role": "user", "content": prompt},
        ],
        "temperature": 0.2,
    }
    req = Request(
        f"{base_url}/chat/completions",
        data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        },
        method="POST",
    )
    timeout = int(os.getenv("REPORT_TRANSLATION_TIMEOUT_SEC", "45"))
    with urlopen(req, timeout=timeout) as resp:
        data = json.loads(resp.read().decode("utf-8"))
    return data.get("choices", [{}])[0].get("message", {}).get("content", "")


def item_haystack(item, content_chars=1600):
    return (
        f"{item.get('company') or ''}\n"
        f"{item.get('title') or ''}\n"
        f"{item.get('url') or ''}\n"
        f"{(item.get('content') or '')[:content_chars]}"
    ).lower()


WEAK_SUMMARY_PHRASES = [
    "背景页",
    "官网级背景页",
    "博客入口",
    "newsroom 入口",
    "新闻聚合入口",
    "趋势页本身",
    "没有稳定提取到",
    "没有结构化提取",
    "缺少明确发布日期",
    "缺少明确发布时间",
    "不是具体公告",
    "不是具体文章",
    "不能形成强投资结论",
    "不能直接作为投资结论",
    "本次抓取到",
    "更接近背景页",
    "当前没有稳定的单一事件正文",
    "作为背景覆盖信号",
    "只能作为背景覆盖信号",
    "只作为观察信号",
    "页面显示",
]


def curated_summary(item):
    haystack = item_haystack(item)
    for keyword, summary in SUMMARY_TRANSLATIONS:
        if keyword in haystack:
            return summary
    return ""


def has_curated_summary(item):
    summary = curated_summary(item)
    return bool(summary) and not is_weak_summary(summary)


def is_weak_summary(summary):
    return any(phrase in summary for phrase in WEAK_SUMMARY_PHRASES)


def has_reportable_content(item):
    if item.get("error"):
        return False
    summary = curated_summary(item)
    if summary and is_weak_summary(summary):
        return False
    content = clean_inline(item.get("content") or "", 240)
    if summary:
        return True
    if not content:
        return False
    weak_markers = [
        "skip to content",
        "no items found",
        "load more",
        "sign up",
        "all news",
        "news archive",
    ]
    lower_content = content.lower()
    if len(content) < 120:
        return False
    if sum(1 for marker in weak_markers if marker in lower_content) >= 2:
        return False
    return True


def should_exclude_from_report(item):
    url = (item.get("url") or "").rstrip("/")
    title = (item.get("title") or "").strip().lower()
    company = item.get("company") or ""

    if "/author/" in url:
        return True

    if company == "Cursor Changelog" and url.endswith("/download"):
        return True

    if company == "Cursor Changelog" and url == "https://cursor.com/changelog":
        return True

    if company == "Arm Newsroom" and title == "see all news":
        return True

    if company == "NVIDIA Developer Blog" and url == "https://developer.nvidia.com" and title == "developer":
        return True

    if company == "Cohere Blog" and url in {"https://cohere.com/products", "https://cohere.com"}:
        return True

    return False


def content_summary(item, max_len=360):
    content = item.get("content") or ""

    if item.get("error"):
        return "该来源抓取失败，本地报告无法读取正文。"

    if not content:
        return "该条没有可用正文，只能作为弱信号处理。"

    llm_lines = llm_article_digest(item)
    if llm_lines:
        return clean_inline("；".join(llm_lines[:3]), max_len)

    summary = curated_summary(item)
    if summary:
        return summary

    content_summary_text = content_based_summary(item)
    if content_summary_text:
        return clean_inline(content_summary_text, max_len)

    return clean_inline(content, max_len)


def company_product(item):
    company = item.get("company") or "未知来源"
    return company


def chinese_event_title(item):
    title = item.get("title") or ""
    company = item.get("company") or "未知来源"
    haystack = item_haystack(item)
    lower_title = title.lower()

    for keyword, translated in TITLE_BY_KEYWORD:
        if keyword in haystack:
            return translated

    for keyword, translated in TITLE_TRANSLATIONS:
        if keyword in haystack:
            return translated

    purpose = PURPOSE_NAMES.get(item.get("purpose") or "", "")
    source_type = TYPE_NAMES.get(item.get("type") or "", "")
    layer = LAYER_NAMES.get(item.get("layer") or "", item.get("layer") or "未知层级")

    if purpose:
        return f"{company}：{purpose}"

    if source_type:
        return f"{company}：{source_type}更新"

    return f"{company}：{layer}信号"


def original_title_line(item):
    title = clean_inline(item.get("title") or "", 180)
    if not title:
        return "- **原文标题**：未提取"
    return f"- **原文标题**：{title}"


def event_type_name(item):
    purpose = item.get("purpose") or ""
    source_type = item.get("type") or ""

    if purpose in PURPOSE_NAMES:
        return PURPOSE_NAMES[purpose]

    if source_type in TYPE_NAMES:
        return TYPE_NAMES[source_type]

    return purpose or source_type or "未知"


def impact_note(item):
    layer = item.get("layer") or "unknown"
    grade = item.get("event_grade") or "unknown"
    purpose = item.get("purpose") or ""

    if grade == "failed_source":
        return "该来源抓取失败，代表当前覆盖存在盲区，需要恢复抓取或替换来源。"

    if grade == "watch_signal":
        return "该条属于发现源信号，目前只能用于观察，不能直接形成强投资结论。"

    if layer == "chips":
        return "该事件与 AI 算力供给、训练/推理效率或硬件生态有关，需要继续跟踪订单、采用和成本指标。"

    if layer == "infrastructure":
        return "该事件与云平台、开发者工具、API 或推理基础设施有关，需要关注企业采用和用量转化。"

    if layer == "models":
        return "该事件与模型能力、模型访问、安全或监管有关，会影响模型厂商竞争格局和客户采购风险。"

    if layer == "applications":
        return "该事件与 AI 应用落地、企业工作流或开发者产品有关，需要关注用户增长、付费转化和留存。"

    if layer == "energy":
        return "该事件与 AI 数据中心能源和物理基础设施有关，需要关注电力约束、订单和项目进度。"

    if layer == "capital" or purpose == "capital_market":
        return "该事件与收入、资本开支、订单、融资或市场预期有关，需要结合财务指标验证。"

    return "该事件需要更多上下文才能判断投资影响。"


def confidence(item):
    if item.get("error"):
        return "低"
    if item.get("detail_fetched") and item.get("published_at"):
        return "高"
    if item.get("published_at"):
        return "中高"
    if item.get("event_grade") == "watch_signal":
        return "低"
    return "中"


def group_items(items):
    grouped = {}
    for item in items:
        grade = item.get("event_grade") or "unknown"
        grouped.setdefault(grade, []).append(item)
    return grouped


def count_by(items, field):
    result = {}
    for item in items:
        key = item.get(field) or "unknown"
        result[key] = result.get(key, 0) + 1
    return result


def format_counts(counts):
    if not counts:
        return "无"
    return "、".join(f"{k}: {v}" for k, v in sorted(counts.items()))


def has_signal(items, keyword):
    keyword = keyword.lower()
    for item in items:
        text = (
            f"{item.get('title') or ''}\n"
            f"{item.get('company') or ''}\n"
            f"{item.get('url') or ''}\n"
            f"{(item.get('content') or '')[:1200]}"
        ).lower()
        if keyword in text:
            return True
    return False


def top_counts(counts, limit=3):
    return sorted(counts.items(), key=lambda item: (-item[1], item[0]))[:limit]


def readable_list(values):
    values = [value for value in values if value]
    if not values:
        return "暂无明确主线"
    if len(values) == 1:
        return values[0]
    return "、".join(values[:-1]) + "和" + values[-1]


def overview_signal_label(item):
    layer = LAYER_NAMES.get(item.get("layer") or "", item.get("layer") or "unknown")
    company = item.get("company") or "未知来源"
    title = clean_inline(chinese_event_title(item), 70)
    return f"{title}（{company}，{layer}）"


def make_core_judgement(confirmed_items, recent_items, watch_items):
    signal_items = confirmed_items + recent_items
    if not signal_items:
        if watch_items:
            return "今天没有抓到可确认的重大事件，主要是发现源和观察信号，适合先做来源验证，不宜直接形成投资判断。"
        return "今天没有形成可用的新信号，日报重点应放在抓取质量、来源可用性和信息盲区排查上。"

    layer_counts = count_by(signal_items, "layer")
    grade_counts = count_by(signal_items, "event_grade")
    dominant_layers = [
        LAYER_NAMES.get(layer, layer)
        for layer, _ in top_counts(layer_counts)
        if layer != "unknown"
    ]
    confirmed_count = grade_counts.get("confirmed_event", 0)
    recent_count = grade_counts.get("recent_signal", 0)

    if confirmed_count:
        strength = f"{confirmed_count} 条 confirmed_event"
        if recent_count:
            strength += f" 和 {recent_count} 条 recent_signal"
    else:
        strength = f"{recent_count} 条 recent_signal"

    return (
        f"今天的有效信号集中在{readable_list(dominant_layers)}，"
        f"共筛出 {strength}；主线应围绕这些层级的事实更新判断，而不是沿用上一日报告的叙事。"
    )


def make_investment_implication(confirmed_items, recent_items):
    signal_items = confirmed_items + recent_items
    if not signal_items:
        return "当前更重要的是恢复有效抓取和确认来源质量；在没有新事实链前，不建议把观察页或失败源解读为投资事件。"

    layer_counts = count_by(signal_items, "layer")
    dominant_layers = [layer for layer, _ in top_counts(layer_counts)]
    implications = []

    if "chips" in dominant_layers:
        implications.append("算力供给、硬件生态和订单验证")
    if "infrastructure" in dominant_layers:
        implications.append("云平台用量、开发者采用和企业部署")
    if "models" in dominant_layers:
        implications.append("模型能力、访问限制、安全合规和客户采购风险")
    if "applications" in dominant_layers:
        implications.append("企业工作流嵌入、付费转化和留存")
    if "energy" in dominant_layers:
        implications.append("电力约束、数据中心项目进度和长期供给")
    if "capital" in dominant_layers:
        implications.append("收入、资本开支、订单和市场预期")

    if not implications:
        implications.append("客户采用、订单/收入影响、第三方验证和后续公告")

    return "短期应重点验证" + "；".join(implications[:3]) + "。"


def make_overview(payload, items):
    confirmed_items = [
        item for item in items
        if item.get("event_grade") == "confirmed_event"
    ]
    recent_items = [
        item for item in items
        if item.get("event_grade") == "recent_signal"
    ]
    watch_items = [
        item for item in items
        if item.get("event_grade") == "watch_signal"
    ]

    topic_lines = []

    if has_signal(confirmed_items, "fable 5") or has_signal(confirmed_items, "mythos 5"):
        topic_lines.append(
            "Anthropic 的 Fable 5 / Mythos 5 被美国政府要求暂停外国国民访问，是今天最重要的风险信号：高能力模型开始直接面对出口控制、国家安全和跨境可用性约束。"
        )

    if (
        has_signal(confirmed_items, "compliance api")
        or has_signal(confirmed_items, "claude design")
        or has_signal(confirmed_items, "role-based")
    ):
        topic_lines.append(
            "Claude 的企业化动作明显加速：Compliance API、角色权限和 Claude Design 分别指向合规审计、组织治理和设计工作流，说明模型厂商正在把竞争从单纯模型能力推进到企业工作台和管理能力。"
        )

    if (
        has_signal(confirmed_items, "agentic coding")
        or has_signal(confirmed_items, "gb300")
        or has_signal(confirmed_items, "minimax m3")
    ):
        topic_lines.append(
            "NVIDIA 的主线是 agentic AI 基础设施：GB300 的 agentic coding 吞吐叙事和 MiniMax M3 长上下文部署方案，都在强化 Blackwell/GB300 不只是训练硬件，而是面向并发 agent、工具调用和长上下文推理的平台。"
        )

    if has_signal(confirmed_items + recent_items, "apigee") or has_signal(recent_items, "colab cli"):
        topic_lines.append(
            "Google 侧信号偏基础设施和开发者工具，重点不是单点爆款产品，而是 Colab CLI、Gemma / DiffusionGemma、Apigee 等能力对本地 AI、agent 可调用算力和企业 API 管理的补齐。"
        )

    if has_signal(recent_items, "amd commits"):
        topic_lines.append(
            "AMD 英国 20 亿英镑 AI 投资仍是近期重要资本与算力信号，说明主权 AI 和科研算力市场继续为 NVIDIA 之外的供应商提供叙事空间，但短期收入转化仍需订单和交付数据验证。"
        )

    if not topic_lines:
        signal_items = confirmed_items + recent_items + watch_items
        for item in signal_items[:4]:
            topic_lines.append(f"{overview_signal_label(item)} 是今天需要跟踪的主要信号。")

    if not topic_lines:
        topic_lines.append("今天没有形成单一压倒性主线，适合先检查来源质量和等待下一次有效抓取。")

    failed_count = len([item for item in items if item.get("event_grade") == "failed_source" or item.get("error")])
    unknown_time_count = len([item for item in items if not item.get("published_at") and not item.get("error")])
    risk_parts = []
    if failed_count:
        risk_parts.append(f"{failed_count} 个来源抓取失败")
    if unknown_time_count:
        risk_parts.append(f"{unknown_time_count} 条缺少明确发布时间")
    if watch_items:
        risk_parts.append(f"{len(watch_items)} 条 discovery 信号仍需验证")
    risk_text = "；".join(risk_parts) if risk_parts else "本次未发现明显 failed_source 或时间盲区。"

    lines = [
        "## 1. 今日总览",
        "",
        f"- **核心判断**：{make_core_judgement(confirmed_items, recent_items, watch_items)}",
        f"- **今日重点**：{topic_lines[0]}",
    ]

    for line in topic_lines[1:]:
        lines.append(f"- **延伸观察**：{line}")

    lines.extend([
        f"- **投资含义**：{make_investment_implication(confirmed_items, recent_items)}",
        f"- **风险提示**：{risk_text}",
        "",
        "---",
        "",
    ])
    return lines


def render_event_section(items, grade, report_date, start_index=1):
    if not items:
        return []

    title = GRADE_TITLES.get(grade, grade)
    lines = [f"## {title}", ""]

    if grade == "recent_signal":
        lines.extend(["**以下事件为近期变化，不是今日事件。**", ""])
    elif grade == "watch_signal":
        lines.extend(["**以下事件来自 discovery 来源，只作为观察信号。**", ""])
    elif grade == "background_ref":
        lines.extend(["**以下内容缺少明确发布时间或更像背景资料，不进入今日重大事件。**", ""])

    for index, item in enumerate(items, start_index):
        heading = clean_inline(chinese_event_title(item), 140)
        lines.extend(
            [
                f"### 事件 {index}：{heading}",
                "",
                f"- **来源 / 公司**：{company_product(item)}",
                original_title_line(item),
                f"- **AI 六层分类**：{item.get('layer') or 'unknown'}",
                f"- **来源角色**：{item.get('source_group') or 'unknown'}",
                f"- **事件类型**：{event_type_name(item)}",
                f"- **发布时间**：{item.get('published_at') or '未知'}",
                f"- **中文摘要**：{content_summary(item)}",
                f"- **新闻详情**：{detail_link(item, report_date)}",
                f"- **投资含义**：{impact_note(item)}",
                f"- **置信度**：{confidence(item)}",
                f"- **来源 URL**：{item.get('url') or item.get('source_url') or '未知'}",
                "",
            ]
        )

        if item.get("error"):
            lines.extend([f"- **错误信息**：{clean_inline(str(item.get('error')), 300)}", ""])

    lines.extend(["---", ""])
    return lines


def render_layer_section(items):
    lines = ["## AI 六层结构变化", ""]
    by_layer = {}
    for item in items:
        by_layer.setdefault(item.get("layer") or "unknown", []).append(item)

    for layer in ["energy", "chips", "infrastructure", "models", "applications", "capital"]:
        layer_items = by_layer.get(layer, [])
        counts = count_by(layer_items, "event_grade")
        lines.extend(
            [
                f"### {LAYER_NAMES[layer]}",
                "",
                f"- **条目数量**：{len(layer_items)}",
                f"- **分级分布**：{format_counts(counts)}",
            ]
        )

        examples = [clean_inline(chinese_event_title(item), 100) for item in layer_items[:3]]
        if examples:
            lines.append(f"- **代表信号**：{'；'.join(examples)}")
        else:
            lines.append("- **代表信号**：无")

        lines.append("")

    unknown_items = by_layer.get("unknown", [])
    if unknown_items:
        lines.extend(
            [
                "### unknown",
                "",
                f"- **条目数量**：{len(unknown_items)}",
                f"- **分级分布**：{format_counts(count_by(unknown_items, 'event_grade'))}",
                "",
            ]
        )

    lines.extend(["---", ""])
    return lines


def render_watch_table(items):
    watch_items = [
        item for item in items
        if item.get("event_grade") == "watch_signal" and has_reportable_content(item)
    ]
    if not watch_items:
        return []

    lines = [
        "## 名单外新增信号汇总",
        "",
        "| 信号 | 来源 | AI 层级 | 为什么值得观察 | 需要什么证据确认 |",
        "|---|---|---|---|---|",
    ]

    for item in watch_items:
        signal = clean_inline(chinese_event_title(item), 80)
        source = clean_inline(item.get("company") or "未知", 40)
        layer = item.get("layer") or "unknown"
        lines.append(
            f"| {signal} | {source} | {layer} | discovery 来源可能发现名单外变化 | 具体对象、发布时间、增长数据、第三方验证 |"
        )

    lines.extend(["", "---", ""])
    return lines


def render_risk_section(items):
    failed = [item for item in items if item.get("event_grade") == "failed_source" or item.get("error")]
    unknown_time = [item for item in items if not item.get("published_at") and not item.get("error")]

    lines = [
        "## 风险信号与信息盲区",
        "",
        "| 类型 | 来源 | 层级 | 问题 | 对日报影响 |",
        "|---|---|---|---|---|",
    ]

    if not failed and not unknown_time:
        lines.append("| 无明显盲区 | - | - | 本次未发现 failed_source 或未知时间条目 | - |")

    for item in failed:
        source = clean_inline(item.get("company") or item.get("url") or "未知", 60)
        layer = item.get("layer") or "unknown"
        problem = clean_inline(str(item.get("error") or "抓取失败"), 90)
        lines.append(f"| 抓取失败 | {source} | {layer} | {problem} | 该层覆盖不足 |")

    for item in unknown_time[:10]:
        source = clean_inline(item.get("company") or item.get("url") or "未知", 60)
        layer = item.get("layer") or "unknown"
        title = clean_inline(chinese_event_title(item), 90)
        lines.append(f"| 时间未知 | {source} | {layer} | {title} | 不能进入今日重大事件 |")

    lines.extend(["", "---", ""])
    return lines


def render_followups(items):
    confirmed = [
        item for item in items
        if item.get("event_grade") == "confirmed_event" and has_reportable_content(item)
    ]
    recent = [
        item for item in items
        if item.get("event_grade") == "recent_signal" and has_reportable_content(item)
    ]
    failed = [item for item in items if item.get("event_grade") == "failed_source" or item.get("error")]

    candidates = confirmed[:5] + recent[:3] + failed[:2]

    lines = [
        "## 明日跟踪清单",
        "",
        "| 优先级 | 层级 | 标的 / 产品 | 跟踪指标 | 原因 |",
        "|---|---|---|---|---|",
    ]

    if not candidates:
        lines.append("| P1 | unknown | 无 | 等待下一次抓取 | 本次没有可跟踪条目 |")

    for index, item in enumerate(candidates, 1):
        priority = "P0" if item.get("event_grade") == "confirmed_event" and index <= 3 else "P1"
        if item.get("error"):
            priority = "P0"
        layer = item.get("layer") or "unknown"
        target = clean_inline(chinese_event_title(item), 70)
        metric = "客户采用、订单/收入影响、第三方验证、后续公告"
        reason = clean_inline(impact_note(item), 80)
        lines.append(f"| {priority} | {layer} | {target} | {metric} | {reason} |")

    lines.extend(
        [
            "",
            "*注：本日报仅供信息参考，不构成投资建议。未形成明确事实链的来源已标注为观察信号或背景参考。*",
            "",
        ]
    )
    return lines


def news_detail_markdown(item, report_date):
    lines = [
        f"# {detail_heading(item)}",
        "",
        f"[返回日报](../../{report_date}.html)",
        "",
        f"- **来源 / 公司**：{company_product(item)}",
        original_title_line(item),
        f"- **AI 六层分类**：{item.get('layer') or 'unknown'}",
        f"- **发布时间**：{item.get('published_at') or '未知'}",
        f"- **原文 URL**：{item.get('url') or item.get('source_url') or '未知'}",
        "",
        "## 中文摘要",
        "",
        content_summary(item),
        "",
        "## 正文中文译文",
        "",
    ]
    for line in translated_detail_lines(item):
        lines.append(f"- {line}")
    lines.extend(["", "---", "", "[返回日报](../../{date}.html)".format(date=report_date), ""])
    return "\n".join(lines)


def write_news_detail_pages(items, report_date):
    detail_items = [
        item for item in items
        if item.get("event_grade") in {"confirmed_event", "recent_signal"} and has_reportable_content(item)
    ]
    detail_dir = NEWS_DETAILS_DIR / report_date
    detail_dir.mkdir(parents=True, exist_ok=True)
    existing = set()
    for item in detail_items:
        path = detail_dir / f"{detail_id(item)}.md"
        path.write_text(news_detail_markdown(item, report_date), encoding="utf-8")
        existing.add(path.name)
    for old in detail_dir.glob("*.md"):
        if old.name not in existing:
            old.unlink()


def generate_report(payload, report_date):
    raw_items = payload.get("items") or []
    items = [
        item for item in raw_items
        if not should_exclude_from_report(item)
    ]
    reportable_items = [
        item for item in items
        if has_reportable_content(item)
    ]
    grouped = group_items(reportable_items)

    lines = [
        f"# AI 投资情报日报 - {report_date}",
        "",
    ]

    lines.extend(make_overview(payload, reportable_items))

    for grade in ["confirmed_event", "recent_signal"]:
        lines.extend(render_event_section(grouped.get(grade, []), grade, report_date))

    lines.extend(render_watch_table(reportable_items))
    lines.extend(render_event_section(grouped.get("background_ref", []), "background_ref", report_date))
    lines.extend(render_layer_section(reportable_items))
    lines.extend(render_risk_section(items))
    lines.extend(render_followups(reportable_items))

    return "\n".join(lines)


def main():
    load_local_env_files()
    args = parse_args()
    input_path = Path(args.input) if args.input else DATA_DIR / f"raw_items_{args.date}.json"
    output_path = Path(args.output) if args.output else REPORTS_DIR / f"{args.date}.md"

    if not input_path.exists():
        raise FileNotFoundError(f"找不到 raw items 文件：{input_path}")

    REPORTS_DIR.mkdir(parents=True, exist_ok=True)

    payload = load_payload(input_path)
    report = generate_report(payload, args.date)
    raw_items = payload.get("items") or []
    reportable_items = [
        item for item in raw_items
        if not should_exclude_from_report(item) and has_reportable_content(item)
    ]
    write_news_detail_pages(reportable_items, args.date)

    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(report, encoding="utf-8")

    print(f"本地日报生成完成：{output_path}")
    print(f"输入文件：{input_path}")
    print(f"内容条目：{len(payload.get('items') or [])}")


if __name__ == "__main__":
    main()
