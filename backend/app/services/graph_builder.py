"""
그래프 구축 서비스.
API 2: Zep API를 사용해 Standalone Graph를 구축한다.
"""

import os
import uuid
import time
import threading
from typing import Dict, Any, List, Optional, Callable
from dataclasses import dataclass
from collections import OrderedDict

from zep_cloud.client import Zep
from zep_cloud import EpisodeData, EntityEdgeSourceTarget

from ..config import Config
from ..models.task import TaskManager, TaskStatus
from ..utils.zep_paging import fetch_all_nodes, fetch_all_edges
from ..utils.llm_client import LLMClient
from .local_graph_repository import LocalGraphRepository
from .text_processor import TextProcessor


@dataclass
class GraphInfo:
    """그래프 정보."""
    graph_id: str
    node_count: int
    edge_count: int
    entity_types: List[str]
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "graph_id": self.graph_id,
            "node_count": self.node_count,
            "edge_count": self.edge_count,
            "entity_types": self.entity_types,
        }


class GraphBuilderService:
    """
    그래프 구축 서비스.
    Zep API를 호출해 지식 그래프를 구축한다.
    """
    
    def __init__(self, api_key: Optional[str] = None, llm_client: Optional[LLMClient] = None):
        self.graph_backend = Config.GRAPH_BACKEND
        self.api_key = api_key or Config.ZEP_API_KEY
        self.local_repo = None
        self.client = None
        self.llm_client = llm_client or LLMClient()
        
        if self.graph_backend == 'local_sqlite':
            self.local_repo = LocalGraphRepository()
        else:
            if not self.api_key:
                raise ValueError("ZEP_API_KEY가 설정되지 않았습니다")
            self.client = Zep(api_key=self.api_key)
        self.task_manager = TaskManager()
    
    def build_graph_async(
        self,
        text: str,
        ontology: Dict[str, Any],
        graph_name: str = "MiroFish Graph",
        chunk_size: int = 500,
        chunk_overlap: int = 50,
        batch_size: int = 3
    ) -> str:
        """
        그래프를 비동기로 구축한다.

        Args:
            text: 입력 텍스트
            ontology: 온톨로지 정의(API 1 결과)
            graph_name: 그래프 이름
            chunk_size: 텍스트 청크 크기
            chunk_overlap: 청크 겹침 크기
            batch_size: 배치당 전송 청크 수

        Returns:
            작업 ID
        """
        if self.graph_backend == 'local_sqlite':
            raise NotImplementedError(
                "local_sqlite 그래프 구축 파이프라인은 아직 연결되지 않았습니다. "
                "현재 slice에서는 repository 계층만 도입되었습니다."
            )
        # 작업 생성
        task_id = self.task_manager.create_task(
            task_type="graph_build",
            metadata={
                "graph_name": graph_name,
                "chunk_size": chunk_size,
                "text_length": len(text),
            }
        )
        
        # 백그라운드 스레드에서 구축 실행
        thread = threading.Thread(
            target=self._build_graph_worker,
            args=(task_id, text, ontology, graph_name, chunk_size, chunk_overlap, batch_size)
        )
        thread.daemon = True
        thread.start()
        
        return task_id
    
    def _build_graph_worker(
        self,
        task_id: str,
        text: str,
        ontology: Dict[str, Any],
        graph_name: str,
        chunk_size: int,
        chunk_overlap: int,
        batch_size: int
    ):
        """그래프 구축 워커 스레드."""
        try:
            self.task_manager.update_task(
                task_id,
                status=TaskStatus.PROCESSING,
                progress=5,
                message="그래프 구축을 시작합니다..."
            )
            
            # 1. 그래프 생성
            graph_id = self.create_graph(graph_name)
            self.task_manager.update_task(
                task_id,
                progress=10,
                message=f"그래프 생성 완료: {graph_id}"
            )
            
            # 2. 온톨로지 설정
            self.set_ontology(graph_id, ontology)
            self.task_manager.update_task(
                task_id,
                progress=15,
                message="온톨로지 설정 완료"
            )
            
            # 3. 텍스트 분할
            chunks = TextProcessor.split_text(text, chunk_size, chunk_overlap)
            total_chunks = len(chunks)
            self.task_manager.update_task(
                task_id,
                progress=20,
                message=f"텍스트를 {total_chunks}개 청크로 분할했습니다"
            )
            
            # 4. 데이터 배치 전송
            episode_uuids = self.add_text_batches(
                graph_id, chunks, batch_size,
                lambda msg, prog: self.task_manager.update_task(
                    task_id,
                    progress=20 + int(prog * 0.4),  # 20-60%
                    message=msg
                )
            )
            
            # 5. Zep 처리 완료 대기
            self.task_manager.update_task(
                task_id,
                progress=60,
                message="Zep 데이터 처리 대기 중..."
            )
            
            self._wait_for_episodes(
                episode_uuids,
                lambda msg, prog: self.task_manager.update_task(
                    task_id,
                    progress=60 + int(prog * 0.3),  # 60-90%
                    message=msg
                )
            )
            
            # 6. 그래프 정보 조회
            self.task_manager.update_task(
                task_id,
                progress=90,
                message="그래프 정보를 가져오는 중..."
            )
            
            graph_info = self._get_graph_info(graph_id)
            
            # 완료
            self.task_manager.complete_task(task_id, {
                "graph_id": graph_id,
                "graph_info": graph_info.to_dict(),
                "chunks_processed": total_chunks,
            })
            
        except Exception as e:
            import traceback
            error_msg = f"{str(e)}\n{traceback.format_exc()}"
            self.task_manager.fail_task(task_id, error_msg)
    
    def create_graph(self, name: str) -> str:
        """Zep 그래프를 생성한다(공개 메서드)."""
        if self.graph_backend == 'local_sqlite':
            return self.local_repo.create_graph(
                name=name,
                description="MiroFish Local Graph"
            )
        graph_id = f"mirofish_{uuid.uuid4().hex[:16]}"
        
        self.client.graph.create(
            graph_id=graph_id,
            name=name,
            description="MiroFish Social Simulation Graph"
        )
        
        return graph_id
    
    def set_ontology(self, graph_id: str, ontology: Dict[str, Any]):
        """그래프 온톨로지를 설정한다(공개 메서드)."""
        if self.graph_backend == 'local_sqlite':
            self.local_repo.save_ontology(graph_id, ontology)
            return
        import warnings
        from typing import Optional
        from pydantic import Field
        from zep_cloud.external_clients.ontology import EntityModel, EntityText, EdgeModel
        
        # Pydantic v2의 Field(default=None) 경고 억제
        # Zep SDK 요구 사항이며 동적 클래스 생성 시 발생하는 경고라 안전하게 무시 가능
        warnings.filterwarnings('ignore', category=UserWarning, module='pydantic')
        
        # Zep 예약 이름(속성명으로 사용 불가)
        RESERVED_NAMES = {'uuid', 'name', 'group_id', 'name_embedding', 'summary', 'created_at'}
        
        def safe_attr_name(attr_name: str) -> str:
            """예약 이름을 안전한 이름으로 변환한다."""
            if attr_name.lower() in RESERVED_NAMES:
                return f"entity_{attr_name}"
            return attr_name
        
        # 엔터티 타입 동적 생성
        entity_types = {}
        for entity_def in ontology.get("entity_types", []):
            name = entity_def["name"]
            description = entity_def.get("description", f"A {name} entity.")
            
            # 속성 dict와 타입 어노테이션 생성(Pydantic v2 필요)
            attrs = {"__doc__": description}
            annotations = {}
            
            for attr_def in entity_def.get("attributes", []):
                attr_name = safe_attr_name(attr_def["name"])  # 안전한 이름 사용
                attr_desc = attr_def.get("description", attr_name)
                # Zep API는 Field description이 필수
                attrs[attr_name] = Field(description=attr_desc, default=None)
                annotations[attr_name] = Optional[EntityText]  # 타입 어노테이션
            
            attrs["__annotations__"] = annotations
            
            # 동적 클래스 생성
            entity_class = type(name, (EntityModel,), attrs)
            entity_class.__doc__ = description
            entity_types[name] = entity_class
        
        # 엣지 타입 동적 생성
        edge_definitions = {}
        for edge_def in ontology.get("edge_types", []):
            name = edge_def["name"]
            description = edge_def.get("description", f"A {name} relationship.")
            
            # 속성 dict와 타입 어노테이션 생성
            attrs = {"__doc__": description}
            annotations = {}
            
            for attr_def in edge_def.get("attributes", []):
                attr_name = safe_attr_name(attr_def["name"])  # 안전한 이름 사용
                attr_desc = attr_def.get("description", attr_name)
                # Zep API는 Field description이 필수
                attrs[attr_name] = Field(description=attr_desc, default=None)
                annotations[attr_name] = Optional[str]  # 엣지 속성은 str 사용
            
            attrs["__annotations__"] = annotations
            
            # 동적 클래스 생성
            class_name = ''.join(word.capitalize() for word in name.split('_'))
            edge_class = type(class_name, (EdgeModel,), attrs)
            edge_class.__doc__ = description
            
            # source_targets 구성
            source_targets = []
            for st in edge_def.get("source_targets", []):
                source_targets.append(
                    EntityEdgeSourceTarget(
                        source=st.get("source", "Entity"),
                        target=st.get("target", "Entity")
                    )
                )
            
            if source_targets:
                edge_definitions[name] = (edge_class, source_targets)
        
        # Zep API로 온톨로지 설정
        if entity_types or edge_definitions:
            self.client.graph.set_ontology(
                graph_ids=[graph_id],
                entities=entity_types if entity_types else None,
                edges=edge_definitions if edge_definitions else None,
            )
    
    def add_text_batches(
        self,
        graph_id: str,
        chunks: List[str],
        batch_size: int = 3,
        progress_callback: Optional[Callable] = None
    ) -> List[str]:
        """텍스트를 그래프에 배치로 추가하고 episode uuid 목록을 반환한다."""
        if self.graph_backend == 'local_sqlite':
            return self._build_local_graph_from_chunks(
                graph_id=graph_id,
                chunks=chunks,
                batch_size=batch_size,
                progress_callback=progress_callback,
            )

        episode_uuids = []
        total_chunks = len(chunks)
        
        for i in range(0, total_chunks, batch_size):
            batch_chunks = chunks[i:i + batch_size]
            batch_num = i // batch_size + 1
            total_batches = (total_chunks + batch_size - 1) // batch_size
            
            if progress_callback:
                progress = (i + len(batch_chunks)) / total_chunks
                progress_callback(
                    f"{batch_num}/{total_batches} 배치 전송 중 ({len(batch_chunks)}개 청크)...",
                    progress
                )
            
            # episode 데이터 생성
            episodes = [
                EpisodeData(data=chunk, type="text")
                for chunk in batch_chunks
            ]
            
            # Zep으로 전송
            try:
                batch_result = self.client.graph.add_batch(
                    graph_id=graph_id,
                    episodes=episodes
                )
                
                # 반환된 episode uuid 수집
                if batch_result and isinstance(batch_result, list):
                    for ep in batch_result:
                        ep_uuid = getattr(ep, 'uuid_', None) or getattr(ep, 'uuid', None)
                        if ep_uuid:
                            episode_uuids.append(ep_uuid)
                
                # 요청 과속 방지
                time.sleep(1)
                
            except Exception as e:
                if progress_callback:
                    progress_callback(f"{batch_num}번 배치 전송 실패: {str(e)}", 0)
                raise
        
        return episode_uuids
    
    def _wait_for_episodes(
        self,
        episode_uuids: List[str],
        progress_callback: Optional[Callable] = None,
        timeout: int = 600
    ):
        """모든 episode 처리 완료를 기다린다(각 episode의 processed 상태 조회)."""
        if self.graph_backend == 'local_sqlite':
            if progress_callback:
                progress_callback("로컬 그래프 저장 완료", 1.0)
            return

        if not episode_uuids:
            if progress_callback:
                progress_callback("대기할 episode가 없습니다", 1.0)
            return
        
        start_time = time.time()
        pending_episodes = set(episode_uuids)
        completed_count = 0
        total_episodes = len(episode_uuids)
        
        if progress_callback:
            progress_callback(f"{total_episodes}개 텍스트 청크 처리 대기 시작...", 0)
        
        while pending_episodes:
            if time.time() - start_time > timeout:
                if progress_callback:
                    progress_callback(
                        f"일부 텍스트 청크가 시간 초과되었습니다. 완료 {completed_count}/{total_episodes}",
                        completed_count / total_episodes
                    )
                break
            
            # 각 episode 처리 상태 확인
            for ep_uuid in list(pending_episodes):
                try:
                    episode = self.client.graph.episode.get(uuid_=ep_uuid)
                    is_processed = getattr(episode, 'processed', False)
                    
                    if is_processed:
                        pending_episodes.remove(ep_uuid)
                        completed_count += 1
                        
                except Exception as e:
                    # 단건 조회 오류는 무시하고 계속 진행
                    pass
            
            elapsed = int(time.time() - start_time)
            if progress_callback:
                progress_callback(
                    f"Zep 처리 중... {completed_count}/{total_episodes} 완료, {len(pending_episodes)}개 대기 ({elapsed}초)",
                    completed_count / total_episodes if total_episodes > 0 else 0
                )
            
            if pending_episodes:
                time.sleep(3)  # 3초마다 확인
        
        if progress_callback:
            progress_callback(f"처리 완료: {completed_count}/{total_episodes}", 1.0)
    
    def _get_graph_info(self, graph_id: str) -> GraphInfo:
        """그래프 정보를 조회한다."""
        if self.graph_backend == 'local_sqlite':
            info = self.local_repo.get_graph_info(graph_id)
            return GraphInfo(
                graph_id=info.graph_id,
                node_count=info.node_count,
                edge_count=info.edge_count,
                entity_types=info.entity_types,
            )
        # 노드 조회(페이지네이션)
        nodes = fetch_all_nodes(self.client, graph_id)

        # 엣지 조회(페이지네이션)
        edges = fetch_all_edges(self.client, graph_id)

        # 엔터티 타입 집계
        entity_types = set()
        for node in nodes:
            if node.labels:
                for label in node.labels:
                    if label not in ["Entity", "Node"]:
                        entity_types.add(label)

        return GraphInfo(
            graph_id=graph_id,
            node_count=len(nodes),
            edge_count=len(edges),
            entity_types=list(entity_types)
        )
    
    def get_graph_data(self, graph_id: str) -> Dict[str, Any]:
        """
        상세 정보를 포함한 전체 그래프 데이터를 조회한다.

        Args:
            graph_id: 그래프 ID

        Returns:
            nodes/edges와 시간/속성 등 상세 정보를 포함한 dict
        """
        if self.graph_backend == 'local_sqlite':
            return self.local_repo.get_graph_data(graph_id)
        nodes = fetch_all_nodes(self.client, graph_id)
        edges = fetch_all_edges(self.client, graph_id)

        # 노드 이름 조회용 매핑 생성
        node_map = {}
        for node in nodes:
            node_map[node.uuid_] = node.name or ""
        
        nodes_data = []
        for node in nodes:
            # 생성 시각
            created_at = getattr(node, 'created_at', None)
            if created_at:
                created_at = str(created_at)
            
            nodes_data.append({
                "uuid": node.uuid_,
                "name": node.name,
                "labels": node.labels or [],
                "summary": node.summary or "",
                "attributes": node.attributes or {},
                "created_at": created_at,
            })
        
        edges_data = []
        for edge in edges:
            # 시간 정보
            created_at = getattr(edge, 'created_at', None)
            valid_at = getattr(edge, 'valid_at', None)
            invalid_at = getattr(edge, 'invalid_at', None)
            expired_at = getattr(edge, 'expired_at', None)
            
            # episodes 조회
            episodes = getattr(edge, 'episodes', None) or getattr(edge, 'episode_ids', None)
            if episodes and not isinstance(episodes, list):
                episodes = [str(episodes)]
            elif episodes:
                episodes = [str(e) for e in episodes]
            
            # fact_type 조회
            fact_type = getattr(edge, 'fact_type', None) or edge.name or ""
            
            edges_data.append({
                "uuid": edge.uuid_,
                "name": edge.name or "",
                "fact": edge.fact or "",
                "fact_type": fact_type,
                "source_node_uuid": edge.source_node_uuid,
                "target_node_uuid": edge.target_node_uuid,
                "source_node_name": node_map.get(edge.source_node_uuid, ""),
                "target_node_name": node_map.get(edge.target_node_uuid, ""),
                "attributes": edge.attributes or {},
                "created_at": str(created_at) if created_at else None,
                "valid_at": str(valid_at) if valid_at else None,
                "invalid_at": str(invalid_at) if invalid_at else None,
                "expired_at": str(expired_at) if expired_at else None,
                "episodes": episodes or [],
            })
        
        return {
            "graph_id": graph_id,
            "nodes": nodes_data,
            "edges": edges_data,
            "node_count": len(nodes_data),
            "edge_count": len(edges_data),
        }
    
    def delete_graph(self, graph_id: str):
        """그래프를 삭제한다."""
        if self.graph_backend == 'local_sqlite':
            self.local_repo.delete_graph(graph_id)
            return
        self.client.graph.delete(graph_id=graph_id)

    def _build_local_graph_from_chunks(
        self,
        graph_id: str,
        chunks: List[str],
        batch_size: int,
        progress_callback: Optional[Callable] = None,
    ) -> List[str]:
        graph = self.local_repo.get_graph(graph_id) or {}
        ontology = graph.get("ontology") or {}
        total_chunks = len(chunks)
        merged_nodes: "OrderedDict[tuple, Dict[str, Any]]" = OrderedDict()
        merged_edges: "OrderedDict[tuple, Dict[str, Any]]" = OrderedDict()
        pseudo_episode_ids: List[str] = []

        for i in range(0, total_chunks, batch_size):
            batch_chunks = chunks[i:i + batch_size]
            batch_num = i // batch_size + 1
            total_batches = (total_chunks + batch_size - 1) // batch_size
            if progress_callback:
                progress_callback(
                    f"로컬 그래프 추출 중 {batch_num}/{total_batches}...",
                    (i + len(batch_chunks)) / max(total_chunks, 1),
                )

            extracted = self._extract_graph_from_text_batch(
                text="\n\n".join(batch_chunks),
                ontology=ontology,
            )
            self._merge_extracted_graph(merged_nodes, merged_edges, extracted)
            pseudo_episode_ids.extend([f"local_{graph_id}_{i+j}" for j in range(len(batch_chunks))])

        self.local_repo.replace_graph_data(
            graph_id=graph_id,
            nodes=list(merged_nodes.values()),
            edges=list(merged_edges.values()),
        )
        return pseudo_episode_ids

    def _extract_graph_from_text_batch(self, text: str, ontology: Dict[str, Any]) -> Dict[str, Any]:
        allowed_entity_types = [e.get("name") for e in ontology.get("entity_types", []) if e.get("name")]
        allowed_edge_types = [e.get("name") for e in ontology.get("edge_types", []) if e.get("name")]

        messages = [
            {
                "role": "system",
                "content": (
                    "당신은 문서에서 지식 그래프 노드와 엣지를 추출하는 시스템입니다. "
                    "반드시 JSON만 반환하세요."
                ),
            },
            {
                "role": "user",
                "content": f"""다음 텍스트에서 엔터티와 관계를 추출하세요.

허용 엔터티 타입: {allowed_entity_types}
허용 관계 타입: {allowed_edge_types}

반환 형식:
{{
  "nodes": [
    {{
      "name": "엔터티명",
      "labels": ["Entity", "타입명"],
      "summary": "요약",
      "attributes": {{}}
    }}
  ],
  "edges": [
    {{
      "name": "관계타입",
      "fact": "관계 사실 한 문장",
      "source_node_name": "출발 엔터티명",
      "target_node_name": "도착 엔터티명",
      "attributes": {{}}
    }}
  ]
}}

텍스트:
\"\"\"
{text[:12000]}
\"\"\"""",
            },
        ]

        try:
            result = self.llm_client.chat_json(messages=messages, temperature=0.2, max_tokens=4096)
            return result if isinstance(result, dict) else {"nodes": [], "edges": []}
        except Exception:
            return {"nodes": [], "edges": []}

    def _merge_extracted_graph(
        self,
        merged_nodes: "OrderedDict[tuple, Dict[str, Any]]",
        merged_edges: "OrderedDict[tuple, Dict[str, Any]]",
        extracted: Dict[str, Any],
    ) -> None:
        node_name_to_uuid: Dict[str, str] = {
            node["name"]: node["uuid"]
            for node in merged_nodes.values()
            if node.get("name")
        }

        for node in extracted.get("nodes", []) or []:
            name = (node.get("name") or "").strip()
            labels = node.get("labels") or ["Entity"]
            if not name:
                continue
            labels = [label for label in labels if label] or ["Entity"]
            if "Entity" not in labels:
                labels.insert(0, "Entity")
            key = (name.lower(), tuple(sorted(labels)))
            if key not in merged_nodes:
                node_uuid = f"local_node_{uuid.uuid4().hex[:12]}"
                merged_nodes[key] = {
                    "uuid": node_uuid,
                    "name": name,
                    "labels": labels,
                    "summary": node.get("summary", ""),
                    "attributes": node.get("attributes", {}) or {},
                    "created_at": None,
                }
                node_name_to_uuid[name] = node_uuid

        for edge in extracted.get("edges", []) or []:
            source_name = (edge.get("source_node_name") or "").strip()
            target_name = (edge.get("target_node_name") or "").strip()
            edge_name = (edge.get("name") or "").strip()
            if not source_name or not target_name or not edge_name:
                continue
            source_uuid = node_name_to_uuid.get(source_name)
            target_uuid = node_name_to_uuid.get(target_name)
            if not source_uuid or not target_uuid:
                continue
            key = (edge_name.lower(), source_uuid, target_uuid, (edge.get("fact") or "").strip().lower())
            if key not in merged_edges:
                merged_edges[key] = {
                    "uuid": f"local_edge_{uuid.uuid4().hex[:12]}",
                    "name": edge_name,
                    "fact": edge.get("fact", ""),
                    "source_node_uuid": source_uuid,
                    "target_node_uuid": target_uuid,
                    "attributes": edge.get("attributes", {}) or {},
                    "created_at": None,
                    "valid_at": None,
                    "invalid_at": None,
                    "expired_at": None,
                    "episodes": [],
                }
