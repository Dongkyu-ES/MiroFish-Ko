"""
Zep도구
그래프검색, 노드읽기, 엣지조회도구, Report Agent

도구():
1. InsightForge()- , 생성질문
2. PanoramaSearch(검색)- , 만료
3. QuickSearch(검색)- 
"""

import time
import json
from typing import Dict, Any, List, Optional
from dataclasses import dataclass, field

from ..config import Config

if Config.GRAPH_BACKEND == "local_primary":
    from backend.bootstrap_graph_backend import bootstrap_graph_backend

    bootstrap_graph_backend()

from zep_cloud.client import Zep

from ..parity_engine.shadow_eval import ShadowEvalCollector
from ..utils.logger import get_logger
from ..utils.llm_client import LLMClient
from ..utils.zep_paging import fetch_all_nodes, fetch_all_edges

logger = get_logger('mirofish.zep_tools')


@dataclass
class SearchResult:
    """검색"""
    facts: List[str]
    edges: List[Dict[str, Any]]
    nodes: List[Dict[str, Any]]
    query: str
    total_count: int
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "facts": self.facts,
            "edges": self.edges,
            "nodes": self.nodes,
            "query": self.query,
            "total_count": self.total_count
        }
    
    def to_text(self) -> str:
        """, LLM"""
        text_parts = [f"검색조회: {self.query}", f" {self.total_count}건정보"]
        
        if self.facts:
            text_parts.append("\n### 사실:")
            for i, fact in enumerate(self.facts, 1):
                text_parts.append(f"{i}. {fact}")
        
        return "\n".join(text_parts)


@dataclass
class NodeInfo:
    """노드정보"""
    uuid: str
    name: str
    labels: List[str]
    summary: str
    attributes: Dict[str, Any]
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "uuid": self.uuid,
            "name": self.name,
            "labels": self.labels,
            "summary": self.summary,
            "attributes": self.attributes
        }
    
    def to_text(self) -> str:
        """"""
        entity_type = next((l for l in self.labels if l not in ["Entity", "Node"]), "타입")
        return f"엔터티: {self.name} (타입: {entity_type})\n요약: {self.summary}"


@dataclass
class EdgeInfo:
    """엣지정보"""
    uuid: str
    name: str
    fact: str
    source_node_uuid: str
    target_node_uuid: str
    source_node_name: Optional[str] = None
    target_node_name: Optional[str] = None
    # 정보
    created_at: Optional[str] = None
    valid_at: Optional[str] = None
    invalid_at: Optional[str] = None
    expired_at: Optional[str] = None
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "uuid": self.uuid,
            "name": self.name,
            "fact": self.fact,
            "source_node_uuid": self.source_node_uuid,
            "target_node_uuid": self.target_node_uuid,
            "source_node_name": self.source_node_name,
            "target_node_name": self.target_node_name,
            "created_at": self.created_at,
            "valid_at": self.valid_at,
            "invalid_at": self.invalid_at,
            "expired_at": self.expired_at
        }
    
    def to_text(self, include_temporal: bool = False) -> str:
        """"""
        source = self.source_node_name or self.source_node_uuid[:8]
        target = self.target_node_name or self.target_node_uuid[:8]
        base_text = f"관계: {source} --[{self.name}]--> {target}\n사실: {self.fact}"
        
        if include_temporal:
            valid_at = self.valid_at or ""
            invalid_at = self.invalid_at or ""
            base_text += f"\n: {valid_at} - {invalid_at}"
            if self.expired_at:
                base_text += f" (만료: {self.expired_at})"
        
        return base_text
    
    @property
    def is_expired(self) -> bool:
        """만료"""
        return self.expired_at is not None
    
    @property
    def is_invalid(self) -> bool:
        """"""
        return self.invalid_at is not None


@dataclass
class InsightForgeResult:
    """
     (InsightForge)
    질문, 분석
    """
    query: str
    simulation_requirement: str
    sub_queries: List[str]
    
    # 
    semantic_facts: List[str] = field(default_factory=list)  # 검색
    entity_insights: List[Dict[str, Any]] = field(default_factory=list)  # 엔터티
    relationship_chains: List[str] = field(default_factory=list)  # 관계 체인
    
    # 정보
    total_facts: int = 0
    total_entities: int = 0
    total_relationships: int = 0
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "query": self.query,
            "simulation_requirement": self.simulation_requirement,
            "sub_queries": self.sub_queries,
            "semantic_facts": self.semantic_facts,
            "entity_insights": self.entity_insights,
            "relationship_chains": self.relationship_chains,
            "total_facts": self.total_facts,
            "total_entities": self.total_entities,
            "total_relationships": self.total_relationships
        }
    
    def to_text(self) -> str:
        """상세, LLM"""
        text_parts = [
            f"## 분석",
            f"분석질문: {self.query}",
            f": {self.simulation_requirement}",
            f"\n### ",
            f"- 사실: {self.total_facts}",
            f"- 엔터티: {self.total_entities}",
            f"- 관계 체인: {self.total_relationships}"
        ]
        
        # 질문
        if self.sub_queries:
            text_parts.append(f"\n### 분석질문")
            for i, sq in enumerate(self.sub_queries, 1):
                text_parts.append(f"{i}. {sq}")
        
        # 검색
        if self.semantic_facts:
            text_parts.append(f"\n### [핵심사실](보고서진행 중)")
            for i, fact in enumerate(self.semantic_facts, 1):
                text_parts.append(f"{i}. \"{fact}\"")
        
        # 엔터티
        if self.entity_insights:
            text_parts.append(f"\n### [엔터티]")
            for entity in self.entity_insights:
                text_parts.append(f"- **{entity.get('name', '')}** ({entity.get('type', '엔터티')})")
                if entity.get('summary'):
                    text_parts.append(f"  요약: \"{entity.get('summary')}\"")
                if entity.get('related_facts'):
                    text_parts.append(f"  사실: {len(entity.get('related_facts', []))}")
        
        # 관계 체인
        if self.relationship_chains:
            text_parts.append(f"\n### [관계 체인]")
            for chain in self.relationship_chains:
                text_parts.append(f"- {chain}")
        
        return "\n".join(text_parts)


@dataclass
class PanoramaResult:
    """
    검색 (Panorama)
    정보, 만료
    """
    query: str
    
    # 노드
    all_nodes: List[NodeInfo] = field(default_factory=list)
    # 엣지(만료)
    all_edges: List[EdgeInfo] = field(default_factory=list)
    # 현재유효사실
    active_facts: List[str] = field(default_factory=list)
    # 만료/사실(과거)
    historical_facts: List[str] = field(default_factory=list)
    
    # 
    total_nodes: int = 0
    total_edges: int = 0
    active_count: int = 0
    historical_count: int = 0
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "query": self.query,
            "all_nodes": [n.to_dict() for n in self.all_nodes],
            "all_edges": [e.to_dict() for e in self.all_edges],
            "active_facts": self.active_facts,
            "historical_facts": self.historical_facts,
            "total_nodes": self.total_nodes,
            "total_edges": self.total_edges,
            "active_count": self.active_count,
            "historical_count": self.historical_count
        }
    
    def to_text(self) -> str:
        """(, )"""
        text_parts = [
            f"## 검색()",
            f"조회: {self.query}",
            f"\n### 정보",
            f"- 노드: {self.total_nodes}",
            f"- 엣지: {self.total_edges}",
            f"- 현재유효사실: {self.active_count}",
            f"- 과거/만료사실: {self.historical_count}"
        ]
        
        # 현재유효사실(, )
        if self.active_facts:
            text_parts.append(f"\n### [현재유효사실](시뮬레이션)")
            for i, fact in enumerate(self.active_facts, 1):
                text_parts.append(f"{i}. \"{fact}\"")
        
        # 과거/만료사실(, )
        if self.historical_facts:
            text_parts.append(f"\n### [과거/만료사실]()")
            for i, fact in enumerate(self.historical_facts, 1):
                text_parts.append(f"{i}. \"{fact}\"")
        
        # 핵심엔터티(, )
        if self.all_nodes:
            text_parts.append(f"\n### [엔터티]")
            for node in self.all_nodes:
                entity_type = next((l for l in node.labels if l not in ["Entity", "Node"]), "엔터티")
                text_parts.append(f"- **{node.name}** ({entity_type})")
        
        return "\n".join(text_parts)


@dataclass
class AgentInterview:
    """Agent 인터뷰"""
    agent_name: str
    agent_role: str  # 타입(:, , )
    agent_bio: str  # 
    question: str  # 인터뷰질문
    response: str  # 인터뷰
    key_quotes: List[str] = field(default_factory=list)  # 핵심
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "agent_name": self.agent_name,
            "agent_role": self.agent_role,
            "agent_bio": self.agent_bio,
            "question": self.question,
            "response": self.response,
            "key_quotes": self.key_quotes
        }
    
    def to_text(self) -> str:
        text = f"**{self.agent_name}** ({self.agent_role})\n"
        # agent_bio, 
        text += f"_: {self.agent_bio}_\n\n"
        text += f"**Q:** {self.question}\n\n"
        text += f"**A:** {self.response}\n"
        if self.key_quotes:
            text += "\n**핵심:**\n"
            for quote in self.key_quotes:
                # 
                clean_quote = quote.replace('\u201c', '').replace('\u201d', '').replace('"', '')
                clean_quote = clean_quote.replace('\u300c', '').replace('\u300d', '')
                clean_quote = clean_quote.strip()
                # 
                while clean_quote and clean_quote[0] in ', ,;;::, .!?\n\r\t ':
                    clean_quote = clean_quote[1:]
                # 질문(질문1-9)
                skip = False
                for d in '123456789':
                    if f'\u95ee\u9898{d}' in clean_quote:
                        skip = True
                        break
                if skip:
                    continue
                # (, )
                if len(clean_quote) > 150:
                    dot_pos = clean_quote.find('\u3002', 80)
                    if dot_pos > 0:
                        clean_quote = clean_quote[:dot_pos + 1]
                    else:
                        clean_quote = clean_quote[:147] + "..."
                if clean_quote and len(clean_quote) >= 10:
                    text += f'> "{clean_quote}"\n'
        return text


@dataclass
class InterviewResult:
    """
    인터뷰 (Interview)
    시뮬레이션Agent 인터뷰
    """
    interview_topic: str  # 인터뷰주제
    interview_questions: List[str]  # 인터뷰질문목록
    
    # 인터뷰선정Agent
    selected_agents: List[Dict[str, Any]] = field(default_factory=list)
    # Agent 인터뷰
    interviews: List[AgentInterview] = field(default_factory=list)
    
    # 선정Agent이유
    selection_reasoning: str = ""
    # 인터뷰요약
    summary: str = ""
    
    # 
    total_agents: int = 0
    interviewed_count: int = 0
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "interview_topic": self.interview_topic,
            "interview_questions": self.interview_questions,
            "selected_agents": self.selected_agents,
            "interviews": [i.to_dict() for i in self.interviews],
            "selection_reasoning": self.selection_reasoning,
            "summary": self.summary,
            "total_agents": self.total_agents,
            "interviewed_count": self.interviewed_count
        }
    
    def to_text(self) -> str:
        """상세, LLM보고서"""
        text_parts = [
            "## 인터뷰보고서",
            f"**인터뷰주제:** {self.interview_topic}",
            f"**인터뷰인원:** {self.interviewed_count} / {self.total_agents} 시뮬레이션Agent",
            "\n### 인터뷰선정 이유",
            self.selection_reasoning or "(선정)",
            "\n---",
            "\n### 인터뷰기록",
        ]

        if self.interviews:
            for i, interview in enumerate(self.interviews, 1):
                text_parts.append(f"\n#### 인터뷰 #{i}: {interview.agent_name}")
                text_parts.append(interview.to_text())
                text_parts.append("\n---")
        else:
            text_parts.append("(인터뷰)\n\n---")

        text_parts.append("\n### 인터뷰요약")
        text_parts.append(self.summary or "(요약)")

        return "\n".join(text_parts)


class ZepToolsService:
    """
    Zep도구
    
    [도구 - ]
    1. insight_forge - (, 생성질문, )
    2. panorama_search - 검색(, 만료)
    3. quick_search - 검색()
    4. interview_agents - 인터뷰(인터뷰시뮬레이션Agent, )
    
    [도구]
    - search_graph - 그래프검색
    - get_all_nodes - 그래프노드
    - get_all_edges - 그래프엣지(정보)
    - get_node_detail - 노드상세정보
    - get_node_edges - 노드엣지
    - get_entities_by_type - 타입엔터티
    - get_entity_summary - 엔터티관계요약
    """
    
    # 설정
    MAX_RETRIES = 3
    RETRY_DELAY = 2.0
    
    def __init__(self, api_key: Optional[str] = None, llm_client: Optional[LLMClient] = None):
        self.api_key = api_key or ("__local__" if Config.GRAPH_BACKEND == "local_primary" else Config.ZEP_API_KEY)
        if Config.GRAPH_BACKEND != "local_primary" and not self.api_key:
            raise ValueError("ZEP_API_KEY 설정")
        
        self.client = Zep(api_key=self.api_key)
        self.shadow_eval = ShadowEvalCollector(
            graph_backend=Config.GRAPH_BACKEND,
            enabled=Config.ENGINE_SHADOW_EVAL_ENABLED,
        )
        # LLMInsightForge생성질문
        self._llm_client = llm_client
        logger.info("ZepToolsService 완료")
    
    @property
    def llm(self) -> LLMClient:
        """LLM"""
        if self._llm_client is None:
            self._llm_client = LLMClient()
        return self._llm_client
    
    def _call_with_retry(self, func, operation_name: str, max_retries: int = None):
        """API호출"""
        max_retries = max_retries or self.MAX_RETRIES
        last_exception = None
        delay = self.RETRY_DELAY
        
        for attempt in range(max_retries):
            try:
                return func()
            except Exception as e:
                last_exception = e
                if not self._is_retryable_error(e):
                    logger.error(f"Zep {operation_name} 영구 실패: {str(e)}")
                    raise
                if attempt < max_retries - 1:
                    logger.warning(
                        f"Zep {operation_name}  {attempt + 1}회실패: {str(e)[:100]}, "
                        f"{delay:.1f}..."
                    )
                    time.sleep(delay)
                    delay *= 2
                else:
                    logger.error(f"Zep {operation_name}  {max_retries}회실패: {str(e)}")
        
        raise last_exception

    def _extract_status_code(self, error: Exception) -> Optional[int]:
        status_code = getattr(error, "status_code", None)
        if isinstance(status_code, int):
            return status_code
        response = getattr(error, "response", None)
        response_status = getattr(response, "status_code", None)
        if isinstance(response_status, int):
            return response_status
        return None

    def _is_retryable_error(self, error: Exception) -> bool:
        if isinstance(error, (ConnectionError, TimeoutError, OSError)):
            return True

        status_code = self._extract_status_code(error)
        if status_code is None:
            return True
        if status_code == 429:
            return True
        if status_code >= 500:
            return True
        return False

    def _should_fallback_to_local_search(self, error: Exception) -> bool:
        if Config.GRAPH_BACKEND == "local_primary":
            return True
        return self._is_retryable_error(error)
    
    def search_graph(
        self, 
        graph_id: str, 
        query: str, 
        limit: int = 10,
        scope: str = "edges"
    ) -> SearchResult:
        """
        그래프검색
        
        검색(+BM25)그래프진행 중정보.
        Zep Cloudsearch API, 핵심.
        
        Args:
            graph_id: 그래프ID (Standalone Graph)
            query: 검색조회
            limit: 반환
            scope: 검색, "edges"  "nodes"
            
        Returns:
            SearchResult: 검색
        """
        logger.info(f"그래프검색: graph_id={graph_id}, query={query[:50]}...")
        
        # Zep Cloud Search API
        try:
            search_results = self._call_with_retry(
                func=lambda: self.client.graph.search(
                    graph_id=graph_id,
                    query=query,
                    limit=limit,
                    scope=scope,
                    reranker="cross_encoder"
                ),
                operation_name=f"그래프검색(graph={graph_id})"
            )
            
            facts = []
            edges = []
            nodes = []
            
            # 엣지검색
            if hasattr(search_results, 'edges') and search_results.edges:
                for edge in search_results.edges:
                    if hasattr(edge, 'fact') and edge.fact:
                        facts.append(edge.fact)
                    edges.append({
                        "uuid": getattr(edge, 'uuid_', None) or getattr(edge, 'uuid', ''),
                        "name": getattr(edge, 'name', ''),
                        "fact": getattr(edge, 'fact', ''),
                        "source_node_uuid": getattr(edge, 'source_node_uuid', ''),
                        "target_node_uuid": getattr(edge, 'target_node_uuid', ''),
                    })
            
            # 노드검색
            if hasattr(search_results, 'nodes') and search_results.nodes:
                for node in search_results.nodes:
                    nodes.append({
                        "uuid": getattr(node, 'uuid_', None) or getattr(node, 'uuid', ''),
                        "name": getattr(node, 'name', ''),
                        "labels": getattr(node, 'labels', []),
                        "summary": getattr(node, 'summary', ''),
                    })
                    # 노드요약사실
                    if hasattr(node, 'summary') and node.summary:
                        facts.append(f"[{node.name}]: {node.summary}")
            
            logger.info(f"검색완료:  {len(facts)}건사실")
            result = SearchResult(
                facts=facts,
                edges=edges,
                nodes=nodes,
                query=query,
                total_count=len(facts)
            )
            self.shadow_eval.capture_search(graph_id, query, limit, scope, result.to_dict())
            return result
            
        except Exception as e:
            logger.warning(f"Zep Search API실패, 검색: {str(e)}")
            if self._should_fallback_to_local_search(e):
                return self._local_search(graph_id, query, limit, scope)
            raise
    
    def _local_search(
        self, 
        graph_id: str, 
        query: str, 
        limit: int = 10,
        scope: str = "edges"
    ) -> SearchResult:
        """
        핵심검색(Zep Search API)
        
        엣지/노드, 핵심
        
        Args:
            graph_id: 그래프ID
            query: 검색조회
            limit: 반환
            scope: 검색
            
        Returns:
            SearchResult: 검색
        """
        logger.info(f"검색: query={query[:30]}...")
        
        facts = []
        edges_result = []
        nodes_result = []
        
        # 조회핵심()
        query_lower = query.lower()
        keywords = [w.strip() for w in query_lower.replace(',', ' ').replace(', ', ' ').split() if len(w.strip()) > 1]
        
        def match_score(text: str) -> int:
            """조회"""
            if not text:
                return 0
            text_lower = text.lower()
            # 조회
            if query_lower in text_lower:
                return 100
            # 핵심
            score = 0
            for keyword in keywords:
                if keyword in text_lower:
                    score += 10
            return score
        
        try:
            if scope in ["edges", "both"]:
                # 엣지
                all_edges = self.get_all_edges(graph_id)
                scored_edges = []
                for edge in all_edges:
                    score = match_score(edge.fact) + match_score(edge.name)
                    if score > 0:
                        scored_edges.append((score, edge))
                
                # 
                scored_edges.sort(key=lambda x: x[0], reverse=True)
                
                for score, edge in scored_edges[:limit]:
                    if edge.fact:
                        facts.append(edge.fact)
                    edges_result.append({
                        "uuid": edge.uuid,
                        "name": edge.name,
                        "fact": edge.fact,
                        "source_node_uuid": edge.source_node_uuid,
                        "target_node_uuid": edge.target_node_uuid,
                    })
            
            if scope in ["nodes", "both"]:
                # 노드
                all_nodes = self.get_all_nodes(graph_id)
                scored_nodes = []
                for node in all_nodes:
                    score = match_score(node.name) + match_score(node.summary)
                    if score > 0:
                        scored_nodes.append((score, node))
                
                scored_nodes.sort(key=lambda x: x[0], reverse=True)
                
                for score, node in scored_nodes[:limit]:
                    nodes_result.append({
                        "uuid": node.uuid,
                        "name": node.name,
                        "labels": node.labels,
                        "summary": node.summary,
                    })
                    if node.summary:
                        facts.append(f"[{node.name}]: {node.summary}")
            
            logger.info(f"검색완료:  {len(facts)}건사실")
            
        except Exception as e:
            logger.error(f"검색실패: {str(e)}")
        
        return SearchResult(
            facts=facts,
            edges=edges_result,
            nodes=nodes_result,
            query=query,
            total_count=len(facts)
        )
    
    def get_all_nodes(self, graph_id: str) -> List[NodeInfo]:
        """
        그래프노드()

        Args:
            graph_id: 그래프ID

        Returns:
            노드목록
        """
        logger.info(f"그래프 {graph_id} 노드...")

        nodes = fetch_all_nodes(self.client, graph_id)

        result = []
        for node in nodes:
            node_uuid = getattr(node, 'uuid_', None) or getattr(node, 'uuid', None) or ""
            result.append(NodeInfo(
                uuid=str(node_uuid) if node_uuid else "",
                name=node.name or "",
                labels=node.labels or [],
                summary=node.summary or "",
                attributes=node.attributes or {}
            ))

        logger.info(f" {len(result)}개노드")
        return result

    def get_all_edges(self, graph_id: str, include_temporal: bool = True) -> List[EdgeInfo]:
        """
        그래프엣지(, 정보)

        Args:
            graph_id: 그래프ID
            include_temporal: 정보(True)

        Returns:
            엣지목록(created_at, valid_at, invalid_at, expired_at)
        """
        logger.info(f"그래프 {graph_id} 엣지...")

        edges = fetch_all_edges(self.client, graph_id)

        result = []
        for edge in edges:
            edge_uuid = getattr(edge, 'uuid_', None) or getattr(edge, 'uuid', None) or ""
            edge_info = EdgeInfo(
                uuid=str(edge_uuid) if edge_uuid else "",
                name=edge.name or "",
                fact=edge.fact or "",
                source_node_uuid=edge.source_node_uuid or "",
                target_node_uuid=edge.target_node_uuid or ""
            )

            # 정보
            if include_temporal:
                edge_info.created_at = getattr(edge, 'created_at', None)
                edge_info.valid_at = getattr(edge, 'valid_at', None)
                edge_info.invalid_at = getattr(edge, 'invalid_at', None)
                edge_info.expired_at = getattr(edge, 'expired_at', None)

            result.append(edge_info)

        logger.info(f" {len(result)}건엣지")
        return result
    
    def get_node_detail(self, node_uuid: str) -> Optional[NodeInfo]:
        """
        노드상세정보
        
        Args:
            node_uuid: 노드UUID
            
        Returns:
            노드정보None
        """
        logger.info(f"노드: {node_uuid[:8]}...")
        
        try:
            node = self._call_with_retry(
                func=lambda: self.client.graph.node.get(uuid_=node_uuid),
                operation_name=f"노드(uuid={node_uuid[:8]}...)"
            )
            
            if not node:
                return None
            
            return NodeInfo(
                uuid=getattr(node, 'uuid_', None) or getattr(node, 'uuid', ''),
                name=node.name or "",
                labels=node.labels or [],
                summary=node.summary or "",
                attributes=node.attributes or {}
            )
        except Exception as e:
            logger.error(f"노드실패: {str(e)}")
            return None
    
    def get_node_edges(self, graph_id: str, node_uuid: str) -> List[EdgeInfo]:
        """
        노드엣지
        
        그래프엣지, 노드엣지
        
        Args:
            graph_id: 그래프ID
            node_uuid: 노드UUID
            
        Returns:
            엣지목록
        """
        logger.info(f"노드 {node_uuid[:8]}... 엣지")
        
        try:
            # 그래프엣지, 
            all_edges = self.get_all_edges(graph_id)
            
            result = []
            for edge in all_edges:
                # 엣지노드()
                if edge.source_node_uuid == node_uuid or edge.target_node_uuid == node_uuid:
                    result.append(edge)
            
            logger.info(f" {len(result)}건노드엣지")
            return result
            
        except Exception as e:
            logger.warning(f"노드엣지실패: {str(e)}")
            return []
    
    def get_entities_by_type(
        self, 
        graph_id: str, 
        entity_type: str
    ) -> List[NodeInfo]:
        """
        타입엔터티
        
        Args:
            graph_id: 그래프ID
            entity_type: 엔터티타입( Student, PublicFigure )
            
        Returns:
            타입엔터티목록
        """
        logger.info(f"타입 {entity_type} 엔터티...")
        
        all_nodes = self.get_all_nodes(graph_id)
        
        filtered = []
        for node in all_nodes:
            # labels타입
            if entity_type in node.labels:
                filtered.append(node)
        
        logger.info(f" {len(filtered)}개 {entity_type} 타입엔터티")
        return filtered
    
    def get_entity_summary(
        self, 
        graph_id: str, 
        entity_name: str
    ) -> Dict[str, Any]:
        """
        엔터티관계요약
        
        검색엔터티정보, 생성요약
        
        Args:
            graph_id: 그래프ID
            entity_name: 엔터티
            
        Returns:
            엔터티요약정보
        """
        logger.info(f"엔터티 {entity_name} 관계요약...")
        
        # 검색엔터티정보
        search_result = self.search_graph(
            graph_id=graph_id,
            query=entity_name,
            limit=20
        )
        
        # 노드진행 중엔터티
        all_nodes = self.get_all_nodes(graph_id)
        entity_node = None
        for node in all_nodes:
            if node.name.lower() == entity_name.lower():
                entity_node = node
                break
        
        related_edges = []
        if entity_node:
            # graph_id파라미터
            related_edges = self.get_node_edges(graph_id, entity_node.uuid)
        
        return {
            "entity_name": entity_name,
            "entity_info": entity_node.to_dict() if entity_node else None,
            "related_facts": search_result.facts,
            "related_edges": [e.to_dict() for e in related_edges],
            "total_relations": len(related_edges)
        }
    
    def get_graph_statistics(self, graph_id: str) -> Dict[str, Any]:
        """
        그래프정보
        
        Args:
            graph_id: 그래프ID
            
        Returns:
            정보
        """
        logger.info(f"그래프 {graph_id} 정보...")
        
        nodes = self.get_all_nodes(graph_id)
        edges = self.get_all_edges(graph_id)
        
        # 엔터티타입
        entity_types = {}
        for node in nodes:
            for label in node.labels:
                if label not in ["Entity", "Node"]:
                    entity_types[label] = entity_types.get(label, 0) + 1
        
        # 관계타입
        relation_types = {}
        for edge in edges:
            relation_types[edge.name] = relation_types.get(edge.name, 0) + 1
        
        return {
            "graph_id": graph_id,
            "total_nodes": len(nodes),
            "total_edges": len(edges),
            "entity_types": entity_types,
            "relation_types": relation_types
        }
    
    def get_simulation_context(
        self, 
        graph_id: str,
        simulation_requirement: str,
        limit: int = 30
    ) -> Dict[str, Any]:
        """
        시뮬레이션정보
        
        검색시뮬레이션정보
        
        Args:
            graph_id: 그래프ID
            simulation_requirement: 시뮬레이션
            limit: 정보
            
        Returns:
            시뮬레이션정보
        """
        logger.info(f"시뮬레이션: {simulation_requirement[:50]}...")
        
        # 검색시뮬레이션정보
        search_result = self.search_graph(
            graph_id=graph_id,
            query=simulation_requirement,
            limit=limit
        )
        
        # 그래프
        stats = self.get_graph_statistics(graph_id)
        
        # 엔터티노드
        all_nodes = self.get_all_nodes(graph_id)
        
        # 타입엔터티(Entity노드)
        entities = []
        for node in all_nodes:
            custom_labels = [l for l in node.labels if l not in ["Entity", "Node"]]
            if custom_labels:
                entities.append({
                    "name": node.name,
                    "type": custom_labels[0],
                    "summary": node.summary
                })
        
        return {
            "simulation_requirement": simulation_requirement,
            "related_facts": search_result.facts,
            "graph_statistics": stats,
            "entities": entities[:limit],  # 
            "total_entities": len(entities)
        }
    
    # ========== 도구() ==========
    
    def insight_forge(
        self,
        graph_id: str,
        query: str,
        simulation_requirement: str,
        report_context: str = "",
        max_sub_queries: int = 5
    ) -> InsightForgeResult:
        """
        [InsightForge - ]
        
        , 질문:
        1. LLM질문질문
        2. 질문검색
        3. 엔터티상세정보
        4. 관계 체인
        5. , 생성
        
        Args:
            graph_id: 그래프ID
            query: 질문
            simulation_requirement: 시뮬레이션
            report_context: 보고서(선택, 질문생성)
            max_sub_queries: 질문
            
        Returns:
            InsightForgeResult: 
        """
        logger.info(f"InsightForge : {query[:50]}...")
        
        result = InsightForgeResult(
            query=query,
            simulation_requirement=simulation_requirement,
            sub_queries=[]
        )
        
        # Step 1: LLM생성질문
        sub_queries = self._generate_sub_queries(
            query=query,
            simulation_requirement=simulation_requirement,
            report_context=report_context,
            max_queries=max_sub_queries
        )
        result.sub_queries = sub_queries
        logger.info(f"생성 {len(sub_queries)}개질문")
        
        # Step 2: 질문검색
        all_facts = []
        all_edges = []
        seen_facts = set()
        
        for sub_query in sub_queries:
            search_result = self.search_graph(
                graph_id=graph_id,
                query=sub_query,
                limit=15,
                scope="edges"
            )
            
            for fact in search_result.facts:
                if fact not in seen_facts:
                    all_facts.append(fact)
                    seen_facts.add(fact)
            
            all_edges.extend(search_result.edges)
        
        # 질문검색
        main_search = self.search_graph(
            graph_id=graph_id,
            query=query,
            limit=20,
            scope="edges"
        )
        for fact in main_search.facts:
            if fact not in seen_facts:
                all_facts.append(fact)
                seen_facts.add(fact)
        
        result.semantic_facts = all_facts
        result.total_facts = len(all_facts)
        
        # Step 3: 엣지진행 중엔터티UUID, 엔터티정보(노드)
        entity_uuids = set()
        for edge_data in all_edges:
            if isinstance(edge_data, dict):
                source_uuid = edge_data.get('source_node_uuid', '')
                target_uuid = edge_data.get('target_node_uuid', '')
                if source_uuid:
                    entity_uuids.add(source_uuid)
                if target_uuid:
                    entity_uuids.add(target_uuid)
        
        # 엔터티(, )
        entity_insights = []
        node_map = {}  # 관계 체인
        
        for uuid in list(entity_uuids):  # 엔터티, 
            if not uuid:
                continue
            try:
                # 노드정보
                node = self.get_node_detail(uuid)
                if node:
                    node_map[uuid] = node
                    entity_type = next((l for l in node.labels if l not in ["Entity", "Node"]), "엔터티")
                    
                    # 엔터티사실()
                    related_facts = [
                        f for f in all_facts 
                        if node.name.lower() in f.lower()
                    ]
                    
                    entity_insights.append({
                        "uuid": node.uuid,
                        "name": node.name,
                        "type": entity_type,
                        "summary": node.summary,
                        "related_facts": related_facts  # , 
                    })
            except Exception as e:
                logger.debug(f"노드 {uuid} 실패: {e}")
                continue
        
        result.entity_insights = entity_insights
        result.total_entities = len(entity_insights)
        
        # Step 4: 관계 체인()
        relationship_chains = []
        for edge_data in all_edges:  # 엣지, 
            if isinstance(edge_data, dict):
                source_uuid = edge_data.get('source_node_uuid', '')
                target_uuid = edge_data.get('target_node_uuid', '')
                relation_name = edge_data.get('name', '')
                
                source_name = node_map.get(source_uuid, NodeInfo('', '', [], '', {})).name or source_uuid[:8]
                target_name = node_map.get(target_uuid, NodeInfo('', '', [], '', {})).name or target_uuid[:8]
                
                chain = f"{source_name} --[{relation_name}]--> {target_name}"
                if chain not in relationship_chains:
                    relationship_chains.append(chain)
        
        result.relationship_chains = relationship_chains
        result.total_relationships = len(relationship_chains)
        
        logger.info(f"InsightForge완료: {result.total_facts}사실, {result.total_entities}엔터티, {result.total_relationships}관계")
        return result
    
    def _generate_sub_queries(
        self,
        query: str,
        simulation_requirement: str,
        report_context: str = "",
        max_queries: int = 5
    ) -> List[str]:
        """
        원 질문을 하위 질문으로 분해해 검색 품질을 높인다.
        """
        system_prompt = """당신은 검색 질의 분해 전문가입니다.

작업:
1. 원 질문을 분석해 핵심 하위 질문 3~5개를 만드세요.
2. 하위 질문은 서로 중복되지 않아야 합니다.
3. 시뮬레이션 맥락(행위자, 관계, 사건)을 반영하세요.
4. JSON만 반환하세요.

반환 형식:
{"sub_queries": ["질문1", "질문2", "..."]}"""

        user_prompt = f"""시뮬레이션 요구사항:
{simulation_requirement}

{f"보고서 맥락: {report_context[:500]}" if report_context else ""}

원 질문:
{query}

최대 {max_queries}개의 하위 질문을 생성하세요."""

        try:
            response = self.llm.chat_json(
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt}
                ],
                temperature=0.3
            )
            
            sub_queries = response.get("sub_queries", [])
            # 목록
            return [str(sq) for sq in sub_queries[:max_queries]]
            
        except Exception as e:
            logger.warning(f"하위 질문 생성 실패: {str(e)}. 원 질문 기반 폴백을 사용합니다.")
            return [
                query,
                f"{query}의 핵심 근거는 무엇인가?",
                f"{query}와 관련된 주요 행위자는 누구인가?",
                f"{query}가 시뮬레이션에 미친 영향은 무엇인가?"
            ][:max_queries]
    
    def panorama_search(
        self,
        graph_id: str,
        query: str,
        include_expired: bool = True,
        limit: int = 50
    ) -> PanoramaResult:
        """
        그래프 전체를 폭넓게 탐색해 현재/과거 사실을 함께 조회한다.

        Args:
            graph_id: 그래프 ID
            query: 검색 질의
            include_expired: 만료/과거 사실 포함 여부
            limit: 반환 개수 제한

        Returns:
            PanoramaResult: 전역 탐색 결과
        """
        logger.info(f"PanoramaSearch 검색: {query[:50]}...")
        
        result = PanoramaResult(query=query)
        
        # 노드
        all_nodes = self.get_all_nodes(graph_id)
        node_map = {n.uuid: n for n in all_nodes}
        result.all_nodes = all_nodes
        result.total_nodes = len(all_nodes)
        
        # 엣지(정보)
        all_edges = self.get_all_edges(graph_id, include_temporal=True)
        result.all_edges = all_edges
        result.total_edges = len(all_edges)
        
        # 사실
        active_facts = []
        historical_facts = []
        
        for edge in all_edges:
            if not edge.fact:
                continue
            
            # 사실엔터티
            source_name = node_map.get(edge.source_node_uuid, NodeInfo('', '', [], '', {})).name or edge.source_node_uuid[:8]
            target_name = node_map.get(edge.target_node_uuid, NodeInfo('', '', [], '', {})).name or edge.target_node_uuid[:8]
            
            # 만료/
            is_historical = edge.is_expired or edge.is_invalid
            
            if is_historical:
                # 과거/만료사실, 
                valid_at = edge.valid_at or ""
                invalid_at = edge.invalid_at or edge.expired_at or ""
                fact_with_time = f"[{valid_at} - {invalid_at}] {edge.fact}"
                historical_facts.append(fact_with_time)
            else:
                # 현재유효사실
                active_facts.append(edge.fact)
        
        # 조회
        query_lower = query.lower()
        keywords = [w.strip() for w in query_lower.replace(',', ' ').replace(', ', ' ').split() if len(w.strip()) > 1]
        
        def relevance_score(fact: str) -> int:
            fact_lower = fact.lower()
            score = 0
            if query_lower in fact_lower:
                score += 100
            for kw in keywords:
                if kw in fact_lower:
                    score += 10
            return score
        
        # 
        active_facts.sort(key=relevance_score, reverse=True)
        historical_facts.sort(key=relevance_score, reverse=True)
        
        result.active_facts = active_facts[:limit]
        result.historical_facts = historical_facts[:limit] if include_expired else []
        result.active_count = len(active_facts)
        result.historical_count = len(historical_facts)
        
        logger.info(f"PanoramaSearch완료: {result.active_count}유효, {result.historical_count}과거")
        return result
    
    def quick_search(
        self,
        graph_id: str,
        query: str,
        limit: int = 10
    ) -> SearchResult:
        """
        단건 질의를 빠르게 조회하는 경량 검색.

        Args:
            graph_id: 그래프 ID
            query: 검색 질의
            limit: 반환 개수 제한

        Returns:
            SearchResult: 검색 결과
        """
        logger.info(f"QuickSearch 검색: {query[:50]}...")
        
        # 호출search_graph
        result = self.search_graph(
            graph_id=graph_id,
            query=query,
            limit=limit,
            scope="edges"
        )
        
        logger.info(f"QuickSearch완료: {result.total_count}")
        return result
    
    def interview_agents(
        self,
        simulation_id: str,
        interview_requirement: str,
        simulation_requirement: str = "",
        max_agents: int = 5,
        custom_questions: List[str] = None
    ) -> InterviewResult:
        """
        OASIS 인터뷰 API를 호출해 시뮬레이션 에이전트를 인터뷰한다.

        흐름:
        1. 프로필 파일 로드
        2. 인터뷰 대상 에이전트 선정
        3. 인터뷰 질문 생성(또는 사용자 질문 사용)
        4. `/api/simulation/interview/batch` 호출
        5. 응답 정리 및 요약 생성

        Args:
            simulation_id: 시뮬레이션 ID
            interview_requirement: 인터뷰 목표/주제
            simulation_requirement: 시뮬레이션 요구사항(선택)
            max_agents: 최대 인터뷰 대상 수
            custom_questions: 사용자 지정 질문 목록(선택)

        Returns:
            InterviewResult: 인터뷰 결과
        """
        from .simulation_runner import SimulationRunner
        
        logger.info(f"InterviewAgents 인터뷰(API): {interview_requirement[:50]}...")
        
        result = InterviewResult(
            interview_topic=interview_requirement,
            interview_questions=custom_questions or []
        )
        
        # Step 1: 읽기파일
        profiles = self._load_agent_profiles(simulation_id)
        
        if not profiles:
            logger.warning(f"시뮬레이션 {simulation_id} 파일")
            result.summary = "인터뷰할 에이전트 프로필 파일을 찾을 수 없습니다."
            return result
        
        result.total_agents = len(profiles)
        logger.info(f"로드 {len(profiles)}개Agent")
        
        # Step 2: LLM선정인터뷰Agent(반환agent_id목록)
        selected_agents, selected_indices, selection_reasoning = self._select_agents_for_interview(
            profiles=profiles,
            interview_requirement=interview_requirement,
            simulation_requirement=simulation_requirement,
            max_agents=max_agents
        )
        
        result.selected_agents = selected_agents
        result.selection_reasoning = selection_reasoning
        logger.info(f"선정 {len(selected_agents)}개Agent 인터뷰: {selected_indices}")
        
        # Step 3: 생성인터뷰질문()
        if not result.interview_questions:
            result.interview_questions = self._generate_interview_questions(
                interview_requirement=interview_requirement,
                simulation_requirement=simulation_requirement,
                selected_agents=selected_agents
            )
            logger.info(f"생성 {len(result.interview_questions)}개인터뷰질문")
        
        # 질문인터뷰prompt
        combined_prompt = "\n".join([f"{i+1}. {q}" for i, q in enumerate(result.interview_questions)])
        
        # , Agent
        INTERVIEW_PROMPT_PREFIX = (
            "아래 질문에 인터뷰 형식으로 답변해 주세요.\n"
            "작성 규칙:\n"
            "1. 도구 호출 JSON은 출력하지 않습니다.\n"
            "2. Markdown 헤더(#, ##, ###)는 사용하지 않습니다.\n"
            "3. 질문 번호(예: '질문1:')는 출력하지 않습니다.\n"
            "4. 각 질문마다 2~3문장으로 구체적으로 답하세요.\n\n"
        )
        optimized_prompt = f"{INTERVIEW_PROMPT_PREFIX}{combined_prompt}"
        
        # Step 4: 호출인터뷰API(platform, 플랫폼 인터뷰)
        try:
            # 인터뷰목록(platform, 플랫폼 인터뷰)
            interviews_request = []
            for agent_idx in selected_indices:
                interviews_request.append({
                    "agent_id": agent_idx,
                    "prompt": optimized_prompt  # prompt
                    # platform, APItwitterreddit플랫폼 인터뷰
                })
            
            logger.info(f"호출인터뷰API(플랫폼): {len(interviews_request)}개Agent")
            
            # 호출 SimulationRunner 인터뷰(platform, 플랫폼 인터뷰)
            api_result = SimulationRunner.interview_agents_batch(
                simulation_id=simulation_id,
                interviews=interviews_request,
                platform=None,  # platform, 플랫폼 인터뷰
                timeout=180.0   # 플랫폼
            )
            
            logger.info(f"인터뷰API반환: {api_result.get('interviews_count', 0)}개, success={api_result.get('success')}")
            
            # API호출
            if not api_result.get("success", False):
                error_msg = api_result.get("error", "오류")
                logger.warning(f"인터뷰API반환실패: {error_msg}")
                result.summary = f"인터뷰 API 호출에 실패했습니다: {error_msg}. OASIS 시뮬레이션 상태를 확인해 주세요."
                return result
            
            # Step 5: API반환, AgentInterview
            # 플랫폼반환: {"twitter_0": {...}, "reddit_0": {...}, "twitter_1": {...}, ...}
            api_data = api_result.get("result", {})
            results_dict = api_data.get("results", {}) if isinstance(api_data, dict) else {}
            
            for i, agent_idx in enumerate(selected_indices):
                agent = selected_agents[i]
                agent_name = agent.get("realname", agent.get("username", f"Agent_{agent_idx}"))
                agent_role = agent.get("profession", "")
                agent_bio = agent.get("bio", "")
                
                # Agent플랫폼 인터뷰
                twitter_result = results_dict.get(f"twitter_{agent_idx}", {})
                reddit_result = results_dict.get(f"reddit_{agent_idx}", {})
                
                twitter_response = twitter_result.get("response", "")
                reddit_response = reddit_result.get("response", "")

                # 도구 호출 JSON 
                twitter_response = self._clean_tool_call_response(twitter_response)
                reddit_response = self._clean_tool_call_response(reddit_response)

                # 플랫폼
                twitter_text = twitter_response if twitter_response else "(플랫폼)"
                reddit_text = reddit_response if reddit_response else "(플랫폼)"
                response_text = f"[Twitter플랫폼]\n{twitter_text}\n\n[Reddit플랫폼]\n{reddit_text}"

                # 핵심(플랫폼)
                import re
                combined_responses = f"{twitter_response} {reddit_response}"

                # 불필요한 마크업/잡음을 정리하고 핵심 문장 추출
                clean_text = re.sub(r'#{1,6}\s+', '', combined_responses)
                clean_text = re.sub(r'\{[^}]*tool_name[^}]*\}', '', clean_text)
                clean_text = re.sub(r'[*_`|>~\-]{2,}', '', clean_text)
                clean_text = re.sub(r'질문\d+:\s*', '', clean_text)
                clean_text = re.sub(r'\[[^\]]+\]', '', clean_text)

                # 1차: 문장 단위 핵심 구절 추출
                sentences = re.split(r'[.!?]', clean_text)
                meaningful = [
                    s.strip() for s in sentences
                    if 20 <= len(s.strip()) <= 150
                    and not re.match(r'^[\s\W,:;]+', s.strip())
                    and not s.strip().startswith(('{', '질문'))
                ]
                meaningful.sort(key=len, reverse=True)
                key_quotes = [s + "." for s in meaningful[:3]]

                # 2차: 따옴표 블록에서 보조 추출
                if not key_quotes:
                    paired = re.findall(r'\u201c([^\u201c\u201d]{15,100})\u201d', clean_text)
                    paired += re.findall(r'\u300c([^\u300c\u300d]{15,100})\u300d', clean_text)
                    key_quotes = [q for q in paired if not re.match(r'^[,:;]+', q)][:3]
                
                interview = AgentInterview(
                    agent_name=agent_name,
                    agent_role=agent_role,
                    agent_bio=agent_bio[:1000],  # bio
                    question=combined_prompt,
                    response=response_text,
                    key_quotes=key_quotes[:5]
                )
                result.interviews.append(interview)
            
            result.interviewed_count = len(result.interviews)
            
        except ValueError as e:
            # 시뮬레이션 실행
            logger.warning(f"인터뷰API호출실패(실행?): {e}")
            result.summary = f"인터뷰에 실패했습니다: {str(e)}. 시뮬레이션이 실행 중인지 확인해 주세요."
            return result
        except Exception as e:
            logger.error(f"인터뷰API호출: {e}")
            import traceback
            logger.error(traceback.format_exc())
            result.summary = f"인터뷰 처리 중 오류가 발생했습니다: {str(e)}"
            return result
        
        # Step 6: 생성인터뷰요약
        if result.interviews:
            result.summary = self._generate_interview_summary(
                interviews=result.interviews,
                interview_requirement=interview_requirement
            )
        
        logger.info(f"InterviewAgents완료: 인터뷰 {result.interviewed_count}개Agent(플랫폼)")
        return result
    
    @staticmethod
    def _clean_tool_call_response(response: str) -> str:
        """에이전트 응답에 섞인 도구 호출 JSON을 텍스트로 정리한다."""
        if not response or not response.strip().startswith('{'):
            return response
        text = response.strip()
        if 'tool_name' not in text[:80]:
            return response
        import re as _re
        try:
            data = json.loads(text)
            if isinstance(data, dict) and 'arguments' in data:
                for key in ('content', 'text', 'body', 'message', 'reply'):
                    if key in data['arguments']:
                        return str(data['arguments'][key])
        except (json.JSONDecodeError, KeyError, TypeError):
            match = _re.search(r'"content"\s*:\s*"((?:[^"\\]|\\.)*)"', text)
            if match:
                return match.group(1).replace('\\n', '\n').replace('\\"', '"')
        return response

    def _load_agent_profiles(self, simulation_id: str) -> List[Dict[str, Any]]:
        """시뮬레이션 디렉터리에서 에이전트 프로필 파일을 로드한다."""
        import os
        import csv
        
        # 파일
        sim_dir = os.path.join(
            os.path.dirname(__file__), 
            f'../../uploads/simulations/{simulation_id}'
        )
        
        profiles = []
        
        # 읽기Reddit JSON
        reddit_profile_path = os.path.join(sim_dir, "reddit_profiles.json")
        if os.path.exists(reddit_profile_path):
            try:
                with open(reddit_profile_path, 'r', encoding='utf-8') as f:
                    profiles = json.load(f)
                logger.info(f" reddit_profiles.json 로드 {len(profiles)}개")
                return profiles
            except Exception as e:
                logger.warning(f"읽기 reddit_profiles.json 실패: {e}")
        
        # 읽기Twitter CSV
        twitter_profile_path = os.path.join(sim_dir, "twitter_profiles.csv")
        if os.path.exists(twitter_profile_path):
            try:
                with open(twitter_profile_path, 'r', encoding='utf-8') as f:
                    reader = csv.DictReader(f)
                    for row in reader:
                        # CSV
                        profiles.append({
                            "realname": row.get("name", ""),
                            "username": row.get("username", ""),
                            "bio": row.get("description", ""),
                            "persona": row.get("user_char", ""),
                            "profession": ""
                        })
                logger.info(f" twitter_profiles.csv 로드 {len(profiles)}개")
                return profiles
            except Exception as e:
                logger.warning(f"읽기 twitter_profiles.csv 실패: {e}")
        
        return profiles
    
    def _select_agents_for_interview(
        self,
        profiles: List[Dict[str, Any]],
        interview_requirement: str,
        simulation_requirement: str,
        max_agents: int
    ) -> tuple:
        """
        인터뷰 목적에 맞는 에이전트를 LLM으로 선정한다.

        Returns:
            tuple: (selected_agents, selected_indices, reasoning)
        """
        
        # 에이전트 요약 목록
        agent_summaries = []
        for i, profile in enumerate(profiles):
            summary = {
                "index": i,
                "name": profile.get("realname", profile.get("username", f"Agent_{i}")),
                "profession": profile.get("profession", ""),
                "bio": profile.get("bio", "")[:200],
                "interested_topics": profile.get("interested_topics", [])
            }
            agent_summaries.append(summary)
        
        system_prompt = """당신은 인터뷰 대상 선정 전문가입니다.

작업:
1. 인터뷰 주제와 가장 관련 있는 에이전트를 고르세요.
2. 서로 다른 관점을 담을 수 있도록 다양성을 고려하세요.
3. 최대 개수 제한을 반드시 지키세요.
4. JSON만 반환하세요.

반환 형식:
{
    "selected_indices": [에이전트 인덱스 목록],
    "reasoning": "선정 이유"
}"""

        user_prompt = f"""인터뷰 주제:
{interview_requirement}

시뮬레이션 요구사항:
{simulation_requirement if simulation_requirement else ""}

후보 에이전트 목록({len(agent_summaries)}명):
{json.dumps(agent_summaries, ensure_ascii=False, indent=2)}

최대 {max_agents}명을 선정하고 이유를 설명하세요."""

        try:
            response = self.llm.chat_json(
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt}
                ],
                temperature=0.3
            )
            
            selected_indices = response.get("selected_indices", [])[:max_agents]
            reasoning = response.get("reasoning", "주제 적합성과 다양성을 기준으로 선정")
            
            # 유효 인덱스만 반영
            selected_agents = []
            valid_indices = []
            for idx in selected_indices:
                if 0 <= idx < len(profiles):
                    selected_agents.append(profiles[idx])
                    valid_indices.append(idx)
            
            return selected_agents, valid_indices, reasoning
            
        except Exception as e:
            logger.warning(f"LLM 에이전트 선정 실패, 앞에서부터 {max_agents}명을 사용합니다: {e}")
            selected = profiles[:max_agents]
            indices = list(range(min(max_agents, len(profiles))))
            return selected, indices, "LLM 실패로 기본 순서로 선정"
    
    def _generate_interview_questions(
        self,
        interview_requirement: str,
        simulation_requirement: str,
        selected_agents: List[Dict[str, Any]]
    ) -> List[str]:
        """인터뷰 질문을 LLM으로 생성한다."""
        
        agent_roles = [a.get("profession", "") for a in selected_agents]
        
        system_prompt = """당신은 인터뷰 질문 설계 전문가입니다.

규칙:
1. 인터뷰 목적에 맞는 질문 3~5개를 생성하세요.
2. 질문은 구체적이고 답변 가능한 형태여야 합니다.
3. 질문 길이는 50자 이내를 권장합니다.
4. 중복 질문을 만들지 마세요.
5. JSON만 반환하세요.

반환 형식:
{"questions": ["질문1", "질문2", "..."]}"""

        user_prompt = f"""인터뷰 요구사항: {interview_requirement}

시뮬레이션 요구사항: {simulation_requirement if simulation_requirement else ""}

대상 역할: {', '.join(agent_roles)}

질문 3~5개를 생성하세요."""

        try:
            response = self.llm.chat_json(
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt}
                ],
                temperature=0.5
            )
            
            return response.get("questions", [f"{interview_requirement}에 대해 설명해 주세요."])
            
        except Exception as e:
            logger.warning(f"생성인터뷰질문실패: {e}")
            return [
                f"{interview_requirement}의 핵심 배경은 무엇인가요?",
                "해당 상황에서 어떤 판단 기준으로 행동했나요?",
                "현재 가장 우려되는 리스크는 무엇인가요?"
            ]
    
    def _generate_interview_summary(
        self,
        interviews: List[AgentInterview],
        interview_requirement: str
    ) -> str:
        """인터뷰 결과를 종합 요약한다."""
        
        if not interviews:
            return "완료된 인터뷰가 없습니다."
        
        # 인터뷰
        interview_texts = []
        for interview in interviews:
            interview_texts.append(f"[{interview.agent_name}({interview.agent_role})]\n{interview.response[:500]}")
        
        system_prompt = """당신은 인터뷰 분석 요약가입니다.

요약 규칙:
1. 핵심 관찰 3~5개를 중심으로 정리하세요.
2. 응답 간 공통점/차이점을 함께 설명하세요.
3. 보고서에 바로 붙여 넣을 수 있는 문장으로 작성하세요.
4. 1000자 이내를 권장합니다.
5. Markdown 헤더(#, ##, ###)는 사용하지 마세요."""

        user_prompt = f"""인터뷰 주제: {interview_requirement}

인터뷰 내용:
{"".join(interview_texts)}

위 내용을 바탕으로 종합 요약을 작성하세요."""

        try:
            summary = self.llm.chat(
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt}
                ],
                temperature=0.3,
                max_tokens=800
            )
            return summary
            
        except Exception as e:
            logger.warning(f"생성인터뷰요약실패: {e}")
            return f"인터뷰 {len(interviews)}건 처리됨. 대상: " + ", ".join([i.agent_name for i in interviews])
