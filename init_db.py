from core.database import engine
from models.base import Base

from models.user import User
from models.resume import Resume
from models.resume_keyword import ResumeKeyword
from models.resume_classification import ResumeClassification
from models.resume_structured import ResumeStructured
from models.question_set import QuestionSet
from models.question import Question
from models.question_filter_result import QuestionFilterResult
from models.llm_run import LlmRun
from models.interview_session import InterviewSession
from models.select_question import SelectQuestion
from models.transcript import Transcript
from models.answer_analysis import AnswerAnalysis
from models.speech_score_summary import SpeechScoreSummary
from models.speech_score_detail import SpeechScoreDetail
from models.speech_feedback import SpeechFeedback


def main():
    Base.metadata.drop_all(bind=engine)
    print("Dropped existing tables.")

    Base.metadata.create_all(bind=engine)
    print("Recreated tables.")


if __name__ == "__main__":
    main()
