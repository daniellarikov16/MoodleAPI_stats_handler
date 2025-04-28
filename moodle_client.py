import requests
from dotenv import load_dotenv
from typing import List, Dict, Tuple, Optional, Union
from datetime import datetime
import os

load_dotenv()

class MoodleClient:
    def __init__(self):
        self.url = os.getenv('MOODLE_URL')
        self.token = os.getenv('MOODLE_TOKEN')
        self.session = requests.Session()

    def call_api(self, function: str, **params) -> Optional[Dict]:
        """
        Получаем данные из API
        """
        params.update({
            'wstoken': self.token,
            'wsfunction': function,
            'moodlewsrestformat': 'json'
        })
        try:
            response = self.session.get(f"{self.url}/webservice/rest/server.php",
                                        params=params)
            response.raise_for_status()
            return response.json()
        except requests.exceptions.RequestException as e:
            print(f"API Error: {e}")
            return None

    def get_user_id_by_username(self, username: str) -> Optional[int]:
        """
        Получает ID пользователя по его имени (username).
        """
        try:
            criteria = [
                {
                    'key': 'email',
                    'value': username
                }
            ]

            params = {
                'criteria[0][key]': 'email',
                'criteria[0][value]': username
            }

            response = self.call_api('core_user_get_users', **params)

            if response['users']:
                user = response['users'][0]
                return user['id']
            else:
                print(f"Пользователь с именем {username} не найден.")
                return None

        except Exception as e:
            print(f"Ответ API: {response}")
            return None

    def get_teacher_courses(self, teacher_id: int, start_date: str, end_date: str) -> Optional[Tuple[List[Dict], int]]:
        """
        Получает список курсов преподавателя за указанный период
        """
        try:
            start_dt = datetime.strptime(start_date, "%Y-%m-%d")
            end_dt = datetime.strptime(end_date, "%Y-%m-%d")

            if start_dt > end_dt:
                raise ValueError("Дата начала периода не может быть позже даты окончания")

            start_timestamp = int(start_dt.timestamp())
            end_timestamp = int(end_dt.timestamp())

            all_courses = self.call_api('core_enrol_get_users_courses', userid=teacher_id)
            if not isinstance(all_courses, list):
                return None

            filtered_courses = []
            for course in all_courses:
                if not all(key in course for key in ['id', 'fullname', 'startdate']):
                    continue

                course_start = course.get('startdate', 0)
                course_end = course.get('enddate', float('inf'))

                if (course_start >= start_timestamp and
                        (course_end <= end_timestamp or course_end == 0)):
                    filtered_courses.append({
                        'id': course['id'],
                        'fullname': course['fullname'],
                        'startdate': datetime.fromtimestamp(course_start).strftime('%Y-%m-%d'),
                        'enddate': datetime.fromtimestamp(course_end).strftime('%Y-%m-%d')
                        if course_end and course_end != float('inf')
                        else 'Не указана'
                    })

            return filtered_courses, len(filtered_courses)

        except ValueError as e:
            print(f"Ошибка формата даты: {e}")
            return None
        except Exception as e:
            print(f"Ошибка при получении курсов: {e}")
            return None

    def track_interim_assessment(self, course_id: int, start_date_str: str, end_date_str: str) -> Optional[Dict]:
        """
        Получение информации о промежуточной аттестации
        """
        try:
            start_date = datetime.strptime(start_date_str, "%Y-%m-%d")
            end_date = datetime.strptime(end_date_str, "%Y-%m-%d")

            grades_data = self.call_api('gradereport_user_get_grade_items', courseid=course_id)
            if not grades_data:
                print("API не вернуло данных")
                return None

            if 'usergrades' not in grades_data or not grades_data['usergrades']:
                print("Нет данных об оценках студентов")
                return None

            unique_items = {}
            for user in grades_data['usergrades']:
                for item in user.get('gradeitems', []):
                    item_id = item['id']
                    if item_id not in unique_items:
                        unique_items[item_id] = item

            interim_items = []
            for item_id, item in unique_items.items():
                try:
                    if not item.get('itemname'):
                        continue

                    item_info = {
                        'id': item_id,
                        'name': item.get('itemname', 'Без названия'),
                        'type': item.get('itemtype', 'unknown'),
                        'max_grade': item.get('grademax', 0)
                    }

                    if not item.get('gradedatesubmitted'):
                        item_info['date'] = 'Дата не указана'
                        interim_items.append(item_info)
                    else:
                        item_date = datetime.fromtimestamp(int(item['gradedatesubmitted']))
                        if start_date <= item_date <= end_date:
                            item_info['date'] = item_date.strftime('%Y-%m-%d')
                            interim_items.append(item_info)

                except Exception as e:
                    print(f"Ошибка обработки элемента оценки {item_id}: {e}")
                    continue

            if not interim_items:
                print("Нет подходящих элементов оценивания")
                return None

            students_grades = []
            for student in grades_data['usergrades']:
                try:
                    student_data = {
                        'userid': student['userid'],
                        'userfullname': student['userfullname'],
                        'grades': []
                    }

                    for item in interim_items:
                        for grade_item in student['gradeitems']:
                            if grade_item['id'] == item['id']:
                                student_data['grades'].append({
                                    'item': item['name'],
                                    'grade': grade_item.get('gradeformatted', '-'),
                                    'percentage': grade_item.get('percentageformatted', '-')
                                })
                                break

                    students_grades.append(student_data)
                except Exception as e:
                    print(f"Ошибка обработки студента {student.get('userid')}: {e}")
                    continue

            return {
                'course_id': course_id,
                'interim_items': interim_items,
                'students_grades': students_grades,
                'period': {
                    'start': start_date_str,
                    'end': end_date_str
                },
                'note': 'Элементы без даты включены в отчет'
            }

        except Exception as e:
            print(f"Ошибка при формировании отчета: {str(e)}")
            return None

    def get_quiz_info(self, quiz_ids: List, course_id: int) -> Dict:
        """
        Получаем информацию о конкретных тестах
        """
        if not quiz_ids:
            print("Не переданы ID тестов")
            return {}

        all_quizzes = self.call_api("mod_quiz_get_quizzes_by_courses", **{"courseids[0]": course_id})

        if not all_quizzes:
            print(f"Не удалось получить тесты для курса {course_id}")
            return {}

        if 'quizzes' not in all_quizzes:
            print(f"Неожиданный формат ответа: {all_quizzes}")
            return {}

        quizzes = all_quizzes.get('quizzes', [])
        return {q['id']: q for q in quizzes if q['id'] in quiz_ids}

    def get_group_students(self, group_id: int) -> List[int]:
        """
        Получаем список ID студентов в группе
        """
        try:
            params = {"groupids[0]": group_id}
            result = self.call_api("core_group_get_group_members", **params)

            if not result:
                print("Пустой ответ от API")
                return []

            if isinstance(result, list) and len(result) > 0:
                first_item = result[0]
                if isinstance(first_item, dict) and 'userids' in first_item:
                    user_ids = first_item['userids']
                    if isinstance(user_ids, list):
                        valid_ids = [uid for uid in user_ids if isinstance(uid, int)]
                        return valid_ids

        except Exception as e:
            print(f"Ошибка при получении студентов: {str(e)}")
            return []

    def get_student_names(self, user_ids: List) -> Dict:
        """
        Получаем имена студентов
        """
        if not user_ids:
            return {}
        params = {'field': 'id'}
        for i, user_id in enumerate(user_ids):
            params[f'values[{i}]'] = user_id

        result = self.call_api("core_user_get_users_by_field", **params)
        return {u['id']: f"{u['firstname']} {u['lastname']}" for u in result} if result else {}

    def get_user_quiz_attempts(self, user_id: int, quiz_ids: List[int]) -> List[Dict]:
        """
        Получает попытки тестов без изменения оригинальных оценок
        """
        attempts = []
        for quiz_id in quiz_ids:
            try:
                result = self.call_api("mod_quiz_get_user_attempts",
                                       quizid=quiz_id,
                                       userid=user_id)

                if result and 'attempts' in result:
                    for attempt in result['attempts']:
                        if attempt.get('state') == 'finished':
                            raw_grade = attempt.get('sumgrades')
                            max_grade = attempt.get('totalmarks')

                            attempts.append({
                                'quiz_id': quiz_id,
                                'raw_grade': raw_grade,
                                'grade': float(raw_grade) if raw_grade is not None else 0.0,
                            })
            except Exception as e:
                print(f"Ошибка в получении оценок {user_id}: {str(e)}")

        return attempts

    def analyze_attempts_results(self, quiz_ids: List[int], group_id: int, course_id: int) -> List[Dict]:
        """
        Анализирует все попытки по всем указанным тестам и возвращает максимальную оценку
        """
        students = self.get_group_students(group_id)
        if not students:
            return []

        student_names = self.get_student_names(students)
        results = []

        for user_id in students:
            all_attempts = []

            for quiz_id in quiz_ids:
                attempts = self.get_user_quiz_attempts(user_id, [quiz_id])
                all_attempts.extend(attempts)

            raw_name = student_names.get(user_id, "Неизвестный")
            clean_name = raw_name.split('@')[0].strip() if '@' in raw_name else raw_name

            if all_attempts:
                best_grade = max(attempt['grade'] for attempt in all_attempts)
                results.append({
                    'user_name': clean_name,
                    'best_grade': best_grade
                })
            else:
                results.append({
                    'user_name': clean_name,
                    'best_grade': 0.0
                })

        return sorted(results, key=lambda x: x['user_name'])

    def get_course_groups(self, course_id: int) -> List:
        """
        Получаем список всех групп в курсе
        """
        response = self.call_api(
            "core_group_get_course_groups",
            courseid=course_id
        )
        groups = response
        valid_groups = []
        for item in groups:
            if isinstance(item, dict):
                valid_groups.append(item)
            else:
                print(f"Пропущен невалидный элемент группы: {item}")

        # Выводим информацию о группах
        print("\nГруппы в курсе:")
        for group in valid_groups:
            print(f"ID: {group.get('id', 'N/A')}, Название: {group.get('name', 'Без названия')}")

        return valid_groups

    def get_group_name(self, group_id: int) -> Optional[str]:
        """
        Получает название группы по её ID
        """
        try:
            params = {"groupids[0]": group_id}
            response = self.call_api("core_group_get_groups", **params)

            if isinstance(response, list) and len(response) > 0:
                return response[0].get('name')

            if isinstance(response, dict):
                if 'groups' in response and len(response['groups']) > 0:
                    return response['groups'][0].get('name')
                if 'exception' in response:
                    print(f"Ошибка API: {response.get('message')}")

            return None

        except Exception as e:
            print(f"Ошибка при получении названия группы: {str(e)}")
            return None