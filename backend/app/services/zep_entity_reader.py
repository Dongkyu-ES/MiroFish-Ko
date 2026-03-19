"""
Zep 엔터티 조회 및 필터링 서비스.
Zep 그래프에서 노드를 읽어 사전 정의한 엔터티 타입에 맞는 노드를 선별한다.
"""

import time
from typing import Dict, Any, List, Optional, Set, Callable, TypeVar
from dataclasses import dataclass, field

from ..config import Config

if Config.GRAPH_BACKEND == "local_primary":
    from backend.bootstrap_graph_backend import bootstrap_graph_backend

    bootstrap_graph_backend()

from zep_cloud.client import Zep

from ..utils.logger import get_logger
from ..utils.zep_paging import fetch_all_nodes, fetch_all_edges

logger = get_logger('mirofish.zep_entity_reader')

# 제네릭 반환 타입
T = TypeVar('T')


@dataclass
class EntityNode:
    """엔터티 노드 데이터 구조."""
    uuid: str
    name: str
    labels: List[str]
    summary: str
    attributes: Dict[str, Any]
    # 연관 엣지 정보
    related_edges: List[Dict[str, Any]] = field(default_factory=list)
    # 연관된 다른 노드 정보
    related_nodes: List[Dict[str, Any]] = field(default_factory=list)
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "uuid": self.uuid,
            "name": self.name,
            "labels": self.labels,
            "summary": self.summary,
            "attributes": self.attributes,
            "related_edges": self.related_edges,
            "related_nodes": self.related_nodes,
        }
    
    def get_entity_type(self) -> Optional[str]:
        """엔터티 타입을 반환한다(`Entity` 기본 라벨 제외)."""
        for label in self.labels:
            if label not in ["Entity", "Node"]:
                return label
        return None


@dataclass
class FilteredEntities:
    """필터링된 엔터티 집합."""
    entities: List[EntityNode]
    entity_types: Set[str]
    total_count: int
    filtered_count: int
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "entities": [e.to_dict() for e in self.entities],
            "entity_types": list(self.entity_types),
            "total_count": self.total_count,
            "filtered_count": self.filtered_count,
        }


class ZepEntityReader:
    """
    Zep 엔터티 조회 및 필터링 서비스.

    주요 기능:
    1. Zep 그래프에서 전체 노드 조회
    2. 사전 정의 타입에 맞는 엔터티 노드 필터링
    3. 엔터티별 연관 엣지/노드 정보 수집
    """
    
    def __init__(self, api_key: Optional[str] = None):
        self.api_key = api_key or ("__local__" if Config.GRAPH_BACKEND == "local_primary" else Config.ZEP_API_KEY)
        if Config.GRAPH_BACKEND != "local_primary" and not self.api_key:
            raise ValueError("ZEP_API_KEY가 설정되지 않았습니다")
        
        self.client = Zep(api_key=self.api_key)
    
    def _call_with_retry(
        self, 
        func: Callable[[], T], 
        operation_name: str,
        max_retries: int = 3,
        initial_delay: float = 2.0
    ) -> T:
        """
        재시도 로직이 포함된 Zep API 호출 래퍼.

        Args:
            func: 실행할 함수(인자 없는 lambda 또는 callable)
            operation_name: 로그용 작업 이름
            max_retries: 최대 재시도 횟수(기본 3회)
            initial_delay: 초기 지연(초)

        Returns:
            API 호출 결과
        """
        last_exception = None
        delay = initial_delay
        
        for attempt in range(max_retries):
            try:
                return func()
            except Exception as e:
                last_exception = e
                if attempt < max_retries - 1:
                    logger.warning(
                        f"Zep {operation_name} {attempt + 1}차 시도 실패: {str(e)[:100]}, "
                        f"{delay:.1f}초 후 재시도..."
                    )
                    time.sleep(delay)
                    delay *= 2  # 지수 백오프
                else:
                    logger.error(f"Zep {operation_name}가 {max_retries}회 시도 후에도 실패: {str(e)}")
        
        raise last_exception
    
    def get_all_nodes(self, graph_id: str) -> List[Dict[str, Any]]:
        """
        그래프의 전체 노드를 조회한다(페이지네이션).

        Args:
            graph_id: 그래프 ID

        Returns:
            노드 목록
        """
        logger.info(f"그래프 {graph_id}의 전체 노드 조회 중...")

        nodes = fetch_all_nodes(self.client, graph_id)

        nodes_data = []
        for node in nodes:
            nodes_data.append({
                "uuid": getattr(node, 'uuid_', None) or getattr(node, 'uuid', ''),
                "name": node.name or "",
                "labels": node.labels or [],
                "summary": node.summary or "",
                "attributes": node.attributes or {},
            })

        logger.info(f"총 {len(nodes_data)}개 노드 조회 완료")
        return nodes_data

    def get_all_edges(self, graph_id: str) -> List[Dict[str, Any]]:
        """
        그래프의 전체 엣지를 조회한다(페이지네이션).

        Args:
            graph_id: 그래프 ID

        Returns:
            엣지 목록
        """
        logger.info(f"그래프 {graph_id}의 전체 엣지 조회 중...")

        edges = fetch_all_edges(self.client, graph_id)

        edges_data = []
        for edge in edges:
            edges_data.append({
                "uuid": getattr(edge, 'uuid_', None) or getattr(edge, 'uuid', ''),
                "name": edge.name or "",
                "fact": edge.fact or "",
                "source_node_uuid": edge.source_node_uuid,
                "target_node_uuid": edge.target_node_uuid,
                "attributes": edge.attributes or {},
            })

        logger.info(f"총 {len(edges_data)}개 엣지 조회 완료")
        return edges_data
    
    def get_node_edges(self, node_uuid: str) -> List[Dict[str, Any]]:
        """
        지정 노드의 연관 엣지를 조회한다(재시도 포함).

        Args:
            node_uuid: 노드 UUID

        Returns:
            엣지 목록
        """
        try:
            node_client = self.client.graph.node
            get_edges = getattr(node_client, "get_edges", None)
            if get_edges is None:
                get_edges = getattr(node_client, "get_entity_edges")

            # 재시도 래퍼로 Zep API 호출
            edges = self._call_with_retry(
                func=lambda: get_edges(node_uuid=node_uuid),
                operation_name=f"노드 엣지 조회(node={node_uuid[:8]}...)"
            )
            
            edges_data = []
            for edge in edges:
                edges_data.append({
                    "uuid": getattr(edge, 'uuid_', None) or getattr(edge, 'uuid', ''),
                    "name": edge.name or "",
                    "fact": edge.fact or "",
                    "source_node_uuid": edge.source_node_uuid,
                    "target_node_uuid": edge.target_node_uuid,
                    "attributes": edge.attributes or {},
                })
            
            return edges_data
        except Exception as e:
            logger.warning(f"노드 {node_uuid} 엣지 조회 실패: {str(e)}")
            return []
    
    def filter_defined_entities(
        self, 
        graph_id: str,
        defined_entity_types: Optional[List[str]] = None,
        enrich_with_edges: bool = True
    ) -> FilteredEntities:
        """
        사전 정의 타입에 맞는 엔터티 노드를 필터링한다.

        필터링 규칙:
        - 라벨이 `Entity`만 있는 노드는 제외
        - `Entity`/`Node` 외 라벨이 있으면 유효 엔터티로 간주

        Args:
            graph_id: 그래프 ID
            defined_entity_types: 사전 정의 엔터티 타입 목록(선택)
            enrich_with_edges: 연관 엣지 정보까지 수집할지 여부

        Returns:
            FilteredEntities
        """
        logger.info(f"그래프 {graph_id} 엔터티 필터링 시작...")
        
        # 전체 노드 조회
        all_nodes = self.get_all_nodes(graph_id)
        total_count = len(all_nodes)
        
        # 전체 엣지 조회(후속 연관 조회용)
        all_edges = self.get_all_edges(graph_id) if enrich_with_edges else []
        
        # 노드 UUID -> 노드 데이터 매핑
        node_map = {n["uuid"]: n for n in all_nodes}
        
        # 조건 충족 엔터티 필터링
        filtered_entities = []
        entity_types_found = set()
        
        for node in all_nodes:
            labels = node.get("labels", [])
            
            # "Entity"/"Node" 외 라벨을 최소 1개 포함해야 함
            custom_labels = [l for l in labels if l not in ["Entity", "Node"]]
            
            if not custom_labels:
                # 기본 라벨만 존재하면 제외
                continue
            
            # 사전 정의 타입 지정 시 매칭 여부 확인
            if defined_entity_types:
                matching_labels = [l for l in custom_labels if l in defined_entity_types]
                if not matching_labels:
                    continue
                entity_type = matching_labels[0]
            else:
                entity_type = custom_labels[0]
            
            entity_types_found.add(entity_type)
            
            # 엔터티 노드 객체 생성
            entity = EntityNode(
                uuid=node["uuid"],
                name=node["name"],
                labels=labels,
                summary=node["summary"],
                attributes=node["attributes"],
            )
            
            # 연관 엣지/노드 정보 수집
            if enrich_with_edges:
                related_edges = []
                related_node_uuids = set()
                
                for edge in all_edges:
                    if edge["source_node_uuid"] == node["uuid"]:
                        related_edges.append({
                            "direction": "outgoing",
                            "edge_name": edge["name"],
                            "fact": edge["fact"],
                            "target_node_uuid": edge["target_node_uuid"],
                        })
                        related_node_uuids.add(edge["target_node_uuid"])
                    elif edge["target_node_uuid"] == node["uuid"]:
                        related_edges.append({
                            "direction": "incoming",
                            "edge_name": edge["name"],
                            "fact": edge["fact"],
                            "source_node_uuid": edge["source_node_uuid"],
                        })
                        related_node_uuids.add(edge["source_node_uuid"])
                
                entity.related_edges = related_edges
                
                # 연결된 노드 기본 정보 조회
                related_nodes = []
                for related_uuid in related_node_uuids:
                    if related_uuid in node_map:
                        related_node = node_map[related_uuid]
                        related_nodes.append({
                            "uuid": related_node["uuid"],
                            "name": related_node["name"],
                            "labels": related_node["labels"],
                            "summary": related_node.get("summary", ""),
                        })
                
                entity.related_nodes = related_nodes
            
            filtered_entities.append(entity)
        
        logger.info(
            f"필터링 완료: 전체 노드 {total_count}, 조건 충족 {len(filtered_entities)}, "
            f"엔터티 타입: {entity_types_found}"
        )
        
        return FilteredEntities(
            entities=filtered_entities,
            entity_types=entity_types_found,
            total_count=total_count,
            filtered_count=len(filtered_entities),
        )
    
    def get_entity_with_context(
        self, 
        graph_id: str, 
        entity_uuid: str
    ) -> Optional[EntityNode]:
        """
        단일 엔터티와 전체 컨텍스트(엣지/연결 노드)를 조회한다.

        Args:
            graph_id: 그래프 ID
            entity_uuid: 엔터티 UUID

        Returns:
            EntityNode 또는 None
        """
        try:
            # 재시도 래퍼로 노드 조회
            node = self._call_with_retry(
                func=lambda: self.client.graph.node.get(uuid_=entity_uuid),
                operation_name=f"노드 상세 조회(uuid={entity_uuid[:8]}...)"
            )
            
            if not node:
                return None
            
            # 노드 엣지 조회
            edges = self.get_node_edges(entity_uuid)
            
            # 연관 노드 조회를 위해 전체 노드 로드
            all_nodes = self.get_all_nodes(graph_id)
            node_map = {n["uuid"]: n for n in all_nodes}
            
            # 연관 엣지/노드 정보 구성
            related_edges = []
            related_node_uuids = set()
            
            for edge in edges:
                if edge["source_node_uuid"] == entity_uuid:
                    related_edges.append({
                        "direction": "outgoing",
                        "edge_name": edge["name"],
                        "fact": edge["fact"],
                        "target_node_uuid": edge["target_node_uuid"],
                    })
                    related_node_uuids.add(edge["target_node_uuid"])
                else:
                    related_edges.append({
                        "direction": "incoming",
                        "edge_name": edge["name"],
                        "fact": edge["fact"],
                        "source_node_uuid": edge["source_node_uuid"],
                    })
                    related_node_uuids.add(edge["source_node_uuid"])
            
            # 연결된 노드 정보 채우기
            related_nodes = []
            for related_uuid in related_node_uuids:
                if related_uuid in node_map:
                    related_node = node_map[related_uuid]
                    related_nodes.append({
                        "uuid": related_node["uuid"],
                        "name": related_node["name"],
                        "labels": related_node["labels"],
                        "summary": related_node.get("summary", ""),
                    })
            
            return EntityNode(
                uuid=getattr(node, 'uuid_', None) or getattr(node, 'uuid', ''),
                name=node.name or "",
                labels=node.labels or [],
                summary=node.summary or "",
                attributes=node.attributes or {},
                related_edges=related_edges,
                related_nodes=related_nodes,
            )
            
        except Exception as e:
            logger.error(f"엔터티 {entity_uuid} 조회 실패: {str(e)}")
            return None
    
    def get_entities_by_type(
        self, 
        graph_id: str, 
        entity_type: str,
        enrich_with_edges: bool = True
    ) -> List[EntityNode]:
        """
        지정 타입의 엔터티를 모두 조회한다.

        Args:
            graph_id: 그래프 ID
            entity_type: 엔터티 타입(예: "Student", "PublicFigure")
            enrich_with_edges: 연관 엣지 정보 포함 여부

        Returns:
            엔터티 목록
        """
        result = self.filter_defined_entities(
            graph_id=graph_id,
            defined_entity_types=[entity_type],
            enrich_with_edges=enrich_with_edges
        )
        return result.entities
