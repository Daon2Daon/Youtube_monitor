"""
YouTube Monitor 스케줄러 서비스 (독립 앱 버전).
APScheduler BackgroundScheduler — YouTube 모니터 잡만 포함.
"""

from __future__ import annotations

from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.jobstores.sqlalchemy import SQLAlchemyJobStore
from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.interval import IntervalTrigger
from typing import Dict, List, Optional
from zoneinfo import ZoneInfo

from app.config import settings


class SchedulerService:
    """YouTube 모니터 잡 스케줄러."""

    def __init__(self):
        jobstores = {
            "default": SQLAlchemyJobStore(url=settings.DATABASE_URL)
        }
        self.scheduler = BackgroundScheduler(
            jobstores=jobstores,
            job_defaults={
                "coalesce": False,
                "max_instances": 3,
            },
            timezone=ZoneInfo("Asia/Seoul"),
        )
        self._running = False

    def start(self):
        if not self._running:
            self.scheduler.start()
            self._running = True
            print("✅ 스케줄러 시작")

    def shutdown(self):
        if self._running:
            self.scheduler.shutdown()
            self._running = False
            print("👋 스케줄러 종료")

    def is_running(self) -> bool:
        return self._running

    def add_cron_job(
        self,
        func,
        job_id: str,
        hour: int,
        minute: int,
        args: Optional[tuple] = None,
        replace_existing: bool = True,
        *,
        misfire_grace_time: Optional[int] = None,
        max_instances: Optional[int] = None,
        coalesce: Optional[bool] = None,
    ):
        trigger = CronTrigger(hour=hour, minute=minute)
        job_kwargs: dict = {
            "func": func,
            "trigger": trigger,
            "id": job_id,
            "args": args or (),
            "replace_existing": replace_existing,
        }
        if misfire_grace_time is not None:
            job_kwargs["misfire_grace_time"] = misfire_grace_time
        if max_instances is not None:
            job_kwargs["max_instances"] = max_instances
        if coalesce is not None:
            job_kwargs["coalesce"] = coalesce
        self.scheduler.add_job(**job_kwargs)
        print(f"📅 Cron Job 등록: {job_id} - 매일 {hour:02d}:{minute:02d}")

    def add_interval_job(
        self,
        func,
        job_id: str,
        minutes: int,
        args: Optional[tuple] = None,
        replace_existing: bool = True,
        max_instances: Optional[int] = None,
    ):
        trigger = IntervalTrigger(minutes=minutes)
        if max_instances is not None:
            self.scheduler.add_job(
                func,
                trigger=trigger,
                id=job_id,
                args=args or (),
                replace_existing=replace_existing,
                max_instances=max_instances,
            )
        else:
            self.scheduler.add_job(
                func,
                trigger=trigger,
                id=job_id,
                args=args or (),
                replace_existing=replace_existing,
            )
        print(f"⏱️  Interval Job 등록: {job_id} - {minutes}분마다 실행")

    def remove_job(self, job_id: str) -> bool:
        try:
            self.scheduler.remove_job(job_id)
            print(f"🗑️  Job 삭제: {job_id}")
            return True
        except Exception as e:
            print(f"❌ Job 삭제 실패: {job_id} - {e}")
            return False

    def get_all_jobs(self) -> List[Dict]:
        jobs = self.scheduler.get_jobs()
        return [
            {
                "id": job.id,
                "name": job.name,
                "next_run_time": (
                    job.next_run_time.isoformat() if job.next_run_time else None
                ),
                "trigger": str(job.trigger),
            }
            for job in jobs
        ]

    def setup_youtube_jobs(self):
        """
        YouTube 모니터 Job 설정.
        - youtube_master_poll: master_interval_min 마다 채널 폴링(신규 영상 DB 적재만)
        - youtube_pending_analysis: pending_analysis_interval_min 마다 미분석 영상 배치 분석
        - youtube_gateway_health: 30분 주기 litellm 헬스체크
        """
        from app.services.youtube.monitor_service import (
            youtube_master_poll_sync,
            youtube_gateway_health_sync,
            youtube_pending_analysis_sync,
        )

        try:
            from app.services.youtube.settings_manager import get_youtube_settings_manager
            mgr = get_youtube_settings_manager()
            polling_cfg = mgr.get_polling()
            poll_interval_min = int(polling_cfg.master_interval_min or 12)
            analysis_interval_min = int(polling_cfg.pending_analysis_interval_min or poll_interval_min)
        except Exception:
            poll_interval_min = 12
            analysis_interval_min = 12

        try:
            self.add_interval_job(
                func=youtube_master_poll_sync,
                job_id="youtube_master_poll",
                minutes=poll_interval_min,
            )
            print(f"✅ YouTube 마스터 폴링 Job 등록: {poll_interval_min}분마다 실행")
        except Exception as e:
            print(f"❌ YouTube 마스터 폴링 Job 등록 실패: {e}")

        try:
            self.add_interval_job(
                func=youtube_pending_analysis_sync,
                job_id="youtube_pending_analysis",
                minutes=analysis_interval_min,
                max_instances=1,
            )
            print(f"✅ YouTube 미분석 배치 분석 Job 등록: {analysis_interval_min}분마다 실행")
        except Exception as e:
            print(f"❌ YouTube 미분석 배치 분석 Job 등록 실패: {e}")

        try:
            self.add_interval_job(
                func=youtube_gateway_health_sync,
                job_id="youtube_gateway_health",
                minutes=30,
            )
            print("✅ YouTube Gateway 헬스체크 Job 등록: 30분마다 실행")
        except Exception as e:
            print(f"❌ YouTube Gateway 헬스체크 Job 등록 실패: {e}")

        # 예약발송 잡도 함께 초기화
        self.setup_youtube_notify_jobs()

    def update_youtube_master_poll_job(self):
        """polling 주기 변경 시 YouTube 폴링/분석 interval 잡만 재등록."""
        from app.services.youtube.monitor_service import (
            youtube_master_poll_sync,
            youtube_pending_analysis_sync,
        )
        try:
            from app.services.youtube.settings_manager import get_youtube_settings_manager
            mgr = get_youtube_settings_manager()
            polling_cfg = mgr.get_polling()
            poll_interval_min = int(polling_cfg.master_interval_min or 12)
            analysis_interval_min = int(polling_cfg.pending_analysis_interval_min or poll_interval_min)
        except Exception:
            poll_interval_min = 12
            analysis_interval_min = 12

        try:
            self.remove_job("youtube_master_poll")
            self.add_interval_job(
                func=youtube_master_poll_sync,
                job_id="youtube_master_poll",
                minutes=poll_interval_min,
            )
            print(f"✅ YouTube 마스터 폴링 Job 재등록: {poll_interval_min}분마다 실행")
        except Exception as e:
            print(f"❌ YouTube 마스터 폴링 Job 업데이트 실패: {e}")

        try:
            self.remove_job("youtube_pending_analysis")
            self.add_interval_job(
                func=youtube_pending_analysis_sync,
                job_id="youtube_pending_analysis",
                minutes=analysis_interval_min,
                max_instances=1,
            )
            print(f"✅ YouTube 미분석 배치 분석 Job 재등록: {analysis_interval_min}분마다 실행")
        except Exception as e:
            print(f"❌ YouTube 미분석 배치 분석 Job 업데이트 실패: {e}")

    def setup_youtube_notify_jobs(self):
        """
        notification.scheduled_times 설정에 따라 예약발송 CronTrigger 잡을 등록한다.
        - send_mode가 'scheduled'가 아니거나 scheduled_times가 비어 있으면 등록하지 않음.
        - 잡 ID 형식: youtube_notify_HHMM (예: youtube_notify_1400)
        """
        import re
        from app.services.youtube.notify_service import youtube_scheduled_notify_sync

        try:
            from app.services.youtube.settings_manager import get_youtube_settings_manager
            mgr = get_youtube_settings_manager()
            notif_cfg = mgr.get_notification()
        except Exception as e:
            print(f"⚠️ YouTube 예약발송 설정 로드 실패: {e}")
            return

        if notif_cfg.send_mode != "scheduled" or not notif_cfg.scheduled_times:
            return

        pattern = re.compile(r"^([01]?\d|2[0-3]):([0-5]\d)$")
        for time_str in notif_cfg.scheduled_times:
            m = pattern.match(time_str)
            if not m:
                print(f"⚠️ YouTube 예약발송: 잘못된 시각 형식 '{time_str}' — skip")
                continue
            hour, minute = int(m.group(1)), int(m.group(2))
            job_id = f"youtube_notify_{hour:02d}{minute:02d}"
            try:
                self.add_cron_job(
                    func=youtube_scheduled_notify_sync,
                    job_id=job_id,
                    hour=hour,
                    minute=minute,
                    misfire_grace_time=3600,
                    max_instances=1,
                    coalesce=True,
                )
                print(f"✅ YouTube 예약발송 Job 등록: {job_id} ({hour:02d}:{minute:02d})")
            except Exception as e:
                print(f"❌ YouTube 예약발송 Job 등록 실패 ({time_str}): {e}")

    def update_youtube_notify_jobs(self):
        """notification 설정 변경 시 기존 예약발송 잡을 전부 제거하고 재등록."""
        try:
            existing_ids = [
                job.id for job in self.scheduler.get_jobs()
                if job.id.startswith("youtube_notify_")
            ]
            for job_id in existing_ids:
                self.remove_job(job_id)
            self.setup_youtube_notify_jobs()
        except Exception as e:
            print(f"❌ YouTube 예약발송 Job 갱신 실패: {e}")


# 싱글톤 인스턴스
scheduler_service = SchedulerService()
