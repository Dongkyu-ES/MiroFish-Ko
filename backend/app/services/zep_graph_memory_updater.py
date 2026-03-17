"""
Zep그래프
시뮬레이션에이전트Zep그래프
"""

import os
import time
import threading
import json
from typing import Dict, Any, List, Optional, Callable
from dataclasses import dataclass
from datetime import datetime
from queue import Queue, Empty

from zep_cloud.client import Zep

from ..config import Config
from ..utils.logger import get_logger
from .local_graph_repository import LocalGraphRepository

logger = get_logger('mirofish.graph_memory_updater')


@dataclass
class AgentActivity:
    """Agent"""
    platform: str           # twitter / reddit
    agent_id: int
    agent_name: str
    action_type: str        # CREATE_POST, LIKE_POST, etc.
    action_args: Dict[str, Any]
    round_num: int
    timestamp: str
    
    def to_episode_text(self) -> str:
        """
        Zep
        
        , Zep엔터티관계
        시뮬레이션, 그래프
        """
        # 타입생성
        action_descriptions = {
            "CREATE_POST": self._describe_create_post,
            "LIKE_POST": self._describe_like_post,
            "DISLIKE_POST": self._describe_dislike_post,
            "REPOST": self._describe_repost,
            "QUOTE_POST": self._describe_quote_post,
            "FOLLOW": self._describe_follow,
            "CREATE_COMMENT": self._describe_create_comment,
            "LIKE_COMMENT": self._describe_like_comment,
            "DISLIKE_COMMENT": self._describe_dislike_comment,
            "SEARCH_POSTS": self._describe_search,
            "SEARCH_USER": self._describe_search_user,
            "MUTE": self._describe_mute,
        }
        
        describe_func = action_descriptions.get(self.action_type, self._describe_generic)
        description = describe_func()
        
        # 최종 표시 형식: "AgentName: 행동 설명"
        return f"{self.agent_name}: {description}"
    
    def _describe_create_post(self) -> str:
        content = self.action_args.get("content", "")
        if content:
            return f"게시글 '{content}'"
        return "게시글 작성"
    
    def _describe_like_post(self) -> str:
        """좋아요 대상 게시글 정보를 정리한다."""
        post_content = self.action_args.get("post_content", "")
        post_author = self.action_args.get("post_author_name", "")
        
        if post_content and post_author:
            return f"{post_author}의 게시글 '{post_content}'"
        if post_content:
            return f"게시글 '{post_content}'"
        if post_author:
            return f"{post_author}의 게시글"
        return "게시글"
    
    def _describe_dislike_post(self) -> str:
        """비추천 대상 게시글 정보를 정리한다."""
        post_content = self.action_args.get("post_content", "")
        post_author = self.action_args.get("post_author_name", "")
        
        if post_content and post_author:
            return f"{post_author}의 게시글 '{post_content}'"
        if post_content:
            return f"게시글 '{post_content}'"
        if post_author:
            return f"{post_author}의 게시글"
        return "게시글"
    
    def _describe_repost(self) -> str:
        """리포스트 대상 원문 정보를 정리한다."""
        original_content = self.action_args.get("original_content", "")
        original_author = self.action_args.get("original_author_name", "")
        
        if original_content and original_author:
            return f"{original_author}의 원문 '{original_content}'"
        if original_content:
            return f"원문 '{original_content}'"
        if original_author:
            return f"{original_author}의 원문"
        return "원문"
    
    def _describe_quote_post(self) -> str:
        """인용 대상 원문과 인용문을 함께 정리한다."""
        original_content = self.action_args.get("original_content", "")
        original_author = self.action_args.get("original_author_name", "")
        quote_content = self.action_args.get("quote_content", "") or self.action_args.get("content", "")
        
        base = ""
        if original_content and original_author:
            base = f"{original_author}의 원문 '{original_content}'"
        elif original_content:
            base = f"원문 '{original_content}'"
        elif original_author:
            base = f"{original_author}의 원문"
        else:
            base = "원문"

        if quote_content:
            base += f", 인용문 '{quote_content}'"
        return base
    
    def _describe_follow(self) -> str:
        """팔로우 대상 사용자를 정리한다."""
        target_user_name = self.action_args.get("target_user_name", "")
        
        if target_user_name:
            return f"사용자 '{target_user_name}'"
        return "사용자"
    
    def _describe_create_comment(self) -> str:
        """댓글 내용과 대상 게시글 정보를 정리한다."""
        content = self.action_args.get("content", "")
        post_content = self.action_args.get("post_content", "")
        post_author = self.action_args.get("post_author_name", "")
        
        if content:
            if post_content and post_author:
                return f"{post_author}의 게시글 '{post_content}'에 댓글 '{content}'"
            elif post_content:
                return f"게시글 '{post_content}'에 댓글 '{content}'"
            elif post_author:
                return f"{post_author}에게 댓글 '{content}'"
            return f"댓글 '{content}'"
        return "댓글 작성"
    
    def _describe_like_comment(self) -> str:
        """좋아요 대상 댓글 정보를 정리한다."""
        comment_content = self.action_args.get("comment_content", "")
        comment_author = self.action_args.get("comment_author_name", "")
        
        if comment_content and comment_author:
            return f"{comment_author}의 댓글 '{comment_content}'"
        if comment_content:
            return f"댓글 '{comment_content}'"
        if comment_author:
            return f"{comment_author}의 댓글"
        return "댓글"
    
    def _describe_dislike_comment(self) -> str:
        """비추천 대상 댓글 정보를 정리한다."""
        comment_content = self.action_args.get("comment_content", "")
        comment_author = self.action_args.get("comment_author_name", "")
        
        if comment_content and comment_author:
            return f"{comment_author}의 댓글 '{comment_content}'"
        if comment_content:
            return f"댓글 '{comment_content}'"
        if comment_author:
            return f"{comment_author}의 댓글"
        return "댓글"
    
    def _describe_search(self) -> str:
        """검색 쿼리를 설명 텍스트로 변환한다."""
        query = self.action_args.get("query", "") or self.action_args.get("keyword", "")
        return f"검색 '{query}'" if query else "검색"
    
    def _describe_search_user(self) -> str:
        """사용자 검색 쿼리를 설명 텍스트로 변환한다."""
        query = self.action_args.get("query", "") or self.action_args.get("username", "")
        return f"검색 '{query}'" if query else "검색"
    
    def _describe_mute(self) -> str:
        """뮤트 대상 사용자를 정리한다."""
        target_user_name = self.action_args.get("target_user_name", "")
        
        if target_user_name:
            return f"사용자 '{target_user_name}'"
        return "사용자"
    
    def _describe_generic(self) -> str:
        # 알 수 없는 타입은 원본 action_type 사용
        return f"{self.action_type}"


class GraphMemoryUpdater:
    """
    시뮬레이션 액션 로그를 읽어 Zep 그래프 메모리를 업데이트한다.

    - 플랫폼별 액션을 배치로 처리
    - action_args의 핵심 맥락을 요약해 메모리 텍스트 생성
    - 재시도/중단 로직 포함
    """
    
    # 플랫폼별 배치 크기
    BATCH_SIZE = 5
    
    # 플랫폼(콘솔)
    PLATFORM_DISPLAY_NAMES = {
        'twitter': '1',
        'reddit': '2',
    }
    
    # (), 요청
    SEND_INTERVAL = 0.5
    
    # 설정
    MAX_RETRIES = 3
    RETRY_DELAY = 2  #초
    
    def __init__(self, graph_id: str, api_key: Optional[str] = None):
        """
        
        
        Args:
            graph_id: Zep그래프ID
            api_key: Zep API Key(선택, 설정읽기)
        """
        self.graph_id = graph_id
        self.graph_backend = Config.GRAPH_BACKEND
        self.api_key = api_key or Config.ZEP_API_KEY
        self.local_repo = None
        self.client = None
        
        if self.graph_backend == 'local_sqlite':
            self.local_repo = LocalGraphRepository()
        else:
            if not self.api_key:
                raise ValueError("ZEP_API_KEY설정")
            self.client = Zep(api_key=self.api_key)
        
        # 
        self._activity_queue: Queue = Queue()
        
        # 플랫폼(플랫폼BATCH_SIZE)
        self._platform_buffers: Dict[str, List[AgentActivity]] = {
            'twitter': [],
            'reddit': [],
        }
        self._buffer_lock = threading.Lock()
        
        # 
        self._running = False
        self._worker_thread: Optional[threading.Thread] = None
        
        # 
        self._total_activities = 0  # 
        self._total_sent = 0        # Zep
        self._total_items_sent = 0  # Zep
        self._failed_count = 0      # 실패
        self._skipped_count = 0     # (DO_NOTHING)
        
        logger.info(f"GraphMemoryUpdater 완료: graph_id={graph_id}, batch_size={self.BATCH_SIZE}")
    
    def _get_platform_display_name(self, platform: str) -> str:
        """플랫폼"""
        return self.PLATFORM_DISPLAY_NAMES.get(platform.lower(), platform)
    
    def start(self):
        """시작"""
        if self._running:
            return
        
        self._running = True
        self._worker_thread = threading.Thread(
            target=self._worker_loop,
            daemon=True,
            name=f"GraphMemoryUpdater-{self.graph_id[:8]}"
        )
        self._worker_thread.start()
        logger.info(f"GraphMemoryUpdater 시작: graph_id={self.graph_id}")
    
    def stop(self):
        """중지"""
        self._running = False
        
        # 
        self._flush_remaining()
        
        if self._worker_thread and self._worker_thread.is_alive():
            self._worker_thread.join(timeout=10)
        
        logger.info(f"GraphMemoryUpdater 중지: graph_id={self.graph_id}, "
                   f"total_activities={self._total_activities}, "
                   f"batches_sent={self._total_sent}, "
                   f"items_sent={self._total_items_sent}, "
                   f"failed={self._failed_count}, "
                   f"skipped={self._skipped_count}")
    
    def add_activity(self, activity: AgentActivity):
        """
        agent
        
        , :
        - CREATE_POST()
        - CREATE_COMMENT()
        - QUOTE_POST()
        - SEARCH_POSTS(검색)
        - SEARCH_USER(검색)
        - LIKE_POST/DISLIKE_POST(/)
        - REPOST()
        - FOLLOW()
        - MUTE()
        - LIKE_COMMENT/DISLIKE_COMMENT(/)
        
        action_args상세 정보(, ).
        
        Args:
            activity: Agent
        """
        # DO_NOTHING타입
        if activity.action_type == "DO_NOTHING":
            self._skipped_count += 1
            return
        
        self._activity_queue.put(activity)
        self._total_activities += 1
        logger.debug(f"Zep: {activity.agent_name} - {activity.action_type}")
    
    def add_activity_from_dict(self, data: Dict[str, Any], platform: str):
        """
        
        
        Args:
            data: actions.jsonl
            platform: 플랫폼 (twitter/reddit)
        """
        # 타입
        if "event_type" in data:
            return
        
        activity = AgentActivity(
            platform=platform,
            agent_id=data.get("agent_id", 0),
            agent_name=data.get("agent_name", ""),
            action_type=data.get("action_type", ""),
            action_args=data.get("action_args", {}),
            round_num=data.get("round", 0),
            timestamp=data.get("timestamp", datetime.now().isoformat()),
        )
        
        self.add_activity(activity)
    
    def _worker_loop(self):
        """ - 플랫폼Zep"""
        while self._running or not self._activity_queue.empty():
            try:
                # (1)
                try:
                    activity = self._activity_queue.get(timeout=1)
                    
                    # 플랫폼
                    platform = activity.platform.lower()
                    with self._buffer_lock:
                        if platform not in self._platform_buffers:
                            self._platform_buffers[platform] = []
                        self._platform_buffers[platform].append(activity)
                        
                        # 플랫폼
                        if len(self._platform_buffers[platform]) >= self.BATCH_SIZE:
                            batch = self._platform_buffers[platform][:self.BATCH_SIZE]
                            self._platform_buffers[platform] = self._platform_buffers[platform][self.BATCH_SIZE:]
                            # 
                            self._send_batch_activities(batch, platform)
                            # , 요청
                            time.sleep(self.SEND_INTERVAL)
                    
                except Empty:
                    pass
                    
            except Exception as e:
                logger.error(f": {e}")
                time.sleep(1)
    
    def _send_batch_activities(self, activities: List[AgentActivity], platform: str):
        """
        Zep그래프()
        
        Args:
            activities: Agent목록
            platform: 플랫폼
        """
        if not activities:
            return
        
        # , 
        episode_texts = [activity.to_episode_text() for activity in activities]
        combined_text = "\n".join(episode_texts)

        if self.graph_backend == 'local_sqlite':
            inserted = self.local_repo.append_activity_batch(
                self.graph_id,
                [
                    {
                        "platform": activity.platform,
                        "agent_id": activity.agent_id,
                        "agent_name": activity.agent_name,
                        "action_type": activity.action_type,
                        "action_args": activity.action_args,
                        "round_num": activity.round_num,
                        "timestamp": activity.timestamp,
                        "fact": activity.to_episode_text(),
                    }
                    for activity in activities
                ],
            )
            self._total_sent += 1
            self._total_items_sent += inserted
            display_name = self._get_platform_display_name(platform)
            logger.info(f" 로컬 그래프 {len(activities)}건{display_name}메모리 반영: {self.graph_id}")
            return
        
        # 
        for attempt in range(self.MAX_RETRIES):
            try:
                self.client.graph.add(
                    graph_id=self.graph_id,
                    type="text",
                    data=combined_text
                )
                
                self._total_sent += 1
                self._total_items_sent += len(activities)
                display_name = self._get_platform_display_name(platform)
                logger.info(f" {len(activities)}건{display_name}그래프 {self.graph_id}")
                logger.debug(f": {combined_text[:200]}...")
                return
                
            except Exception as e:
                if attempt < self.MAX_RETRIES - 1:
                    logger.warning(f"Zep실패 ( {attempt + 1}/{self.MAX_RETRIES}): {e}")
                    time.sleep(self.RETRY_DELAY * (attempt + 1))
                else:
                    logger.error(f"Zep실패, {self.MAX_RETRIES}: {e}")
                    self._failed_count += 1
    
    def _flush_remaining(self):
        """진행 중"""
        # 진행 중, 
        while not self._activity_queue.empty():
            try:
                activity = self._activity_queue.get_nowait()
                platform = activity.platform.lower()
                with self._buffer_lock:
                    if platform not in self._platform_buffers:
                        self._platform_buffers[platform] = []
                    self._platform_buffers[platform].append(activity)
            except Empty:
                break
        
        # 플랫폼진행 중(BATCH_SIZE)
        with self._buffer_lock:
            for platform, buffer in self._platform_buffers.items():
                if buffer:
                    display_name = self._get_platform_display_name(platform)
                    logger.info(f"{display_name}플랫폼 {len(buffer)}건")
                    self._send_batch_activities(buffer, platform)
            # 
            for platform in self._platform_buffers:
                self._platform_buffers[platform] = []
    
    def get_stats(self) -> Dict[str, Any]:
        """정보"""
        with self._buffer_lock:
            buffer_sizes = {p: len(b) for p, b in self._platform_buffers.items()}
        
        return {
            "graph_id": self.graph_id,
            "batch_size": self.BATCH_SIZE,
            "total_activities": self._total_activities,  # 
            "batches_sent": self._total_sent,            # 
            "items_sent": self._total_items_sent,        # 
            "failed_count": self._failed_count,          # 실패
            "skipped_count": self._skipped_count,        # (DO_NOTHING)
            "queue_size": self._activity_queue.qsize(),
            "buffer_sizes": buffer_sizes,                # 플랫폼
            "running": self._running,
        }


class GraphMemoryManager:
    """
    시뮬레이션Zep그래프
    
    시뮬레이션
    """
    
    _updaters: Dict[str, GraphMemoryUpdater] = {}
    _lock = threading.Lock()
    
    @classmethod
    def create_updater(cls, simulation_id: str, graph_id: str) -> GraphMemoryUpdater:
        """
        시뮬레이션그래프
        
        Args:
            simulation_id: 시뮬레이션ID
            graph_id: Zep그래프ID
            
        Returns:
            GraphMemoryUpdater
        """
        with cls._lock:
            # , 중지
            if simulation_id in cls._updaters:
                cls._updaters[simulation_id].stop()
            
            updater = GraphMemoryUpdater(graph_id)
            updater.start()
            cls._updaters[simulation_id] = updater
            
            logger.info(f"그래프: simulation_id={simulation_id}, graph_id={graph_id}")
            return updater
    
    @classmethod
    def get_updater(cls, simulation_id: str) -> Optional[GraphMemoryUpdater]:
        """시뮬레이션"""
        return cls._updaters.get(simulation_id)
    
    @classmethod
    def stop_updater(cls, simulation_id: str):
        """중지시뮬레이션"""
        with cls._lock:
            if simulation_id in cls._updaters:
                cls._updaters[simulation_id].stop()
                del cls._updaters[simulation_id]
                logger.info(f"중지그래프: simulation_id={simulation_id}")
    
    #  stop_all 호출
    _stop_all_done = False
    
    @classmethod
    def stop_all(cls):
        """중지"""
        # 호출
        if cls._stop_all_done:
            return
        cls._stop_all_done = True
        
        with cls._lock:
            if cls._updaters:
                for simulation_id, updater in list(cls._updaters.items()):
                    try:
                        updater.stop()
                    except Exception as e:
                        logger.error(f"중지실패: simulation_id={simulation_id}, error={e}")
                cls._updaters.clear()
            logger.info("중지그래프")
    
    @classmethod
    def get_all_stats(cls) -> Dict[str, Dict[str, Any]]:
        """정보"""
        return {
            sim_id: updater.get_stats() 
            for sim_id, updater in cls._updaters.items()
        }


# Backward-compatible aliases during migration
ZepGraphMemoryUpdater = GraphMemoryUpdater
ZepGraphMemoryManager = GraphMemoryManager
