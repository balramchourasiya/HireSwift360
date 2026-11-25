export const demoCompany = { name: 'HireSwift Demo' };

export const demoCandidates = [
  {
    id: 1,
    full_name: 'Aarav Sharma',
    email: 'aarav.sharma@example.test',
    location: 'Bengaluru',
    education: 'B.Tech, Computer Science',
    graduation_year: 2022,
    experience_years: 4,
    skills: ['Python', 'FastAPI', 'PostgreSQL', 'Docker'],
    status: 'Interview',
  },
  {
    id: 2,
    full_name: 'Meera Nair',
    email: 'meera.nair@example.test',
    location: 'Pune',
    education: 'M.Tech, Software Engineering',
    graduation_year: 2021,
    experience_years: 5,
    skills: ['React', 'TypeScript', 'Node.js', 'AWS'],
    status: 'Shortlisted',
  },
  {
    id: 3,
    full_name: 'Kabir Rao',
    email: 'kabir.rao@example.test',
    location: 'Hyderabad',
    education: 'B.E., Information Technology',
    graduation_year: 2023,
    experience_years: 3,
    skills: ['Python', 'SQL', 'Machine Learning', 'FastAPI'],
    status: 'Applied',
  },
  {
    id: 4,
    full_name: 'Ananya Iyer',
    email: 'ananya.iyer@example.test',
    location: 'Remote',
    education: 'B.Tech, Electronics',
    graduation_year: 2020,
    experience_years: 6,
    skills: ['Java', 'Spring Boot', 'PostgreSQL', 'Kubernetes'],
    status: 'Offer',
  },
];

export const demoJobs = [
  {
    id: 1,
    title: 'Backend Engineer',
    department: 'Engineering',
    location: 'Bengaluru / Remote',
    description: 'Build reliable APIs and data services for the hiring platform.',
    required_skills: ['Python', 'FastAPI', 'PostgreSQL'],
    min_experience: 3,
  },
  {
    id: 2,
    title: 'Frontend Engineer',
    department: 'Product Engineering',
    location: 'Remote',
    description: 'Create accessible, responsive recruiter and candidate experiences.',
    required_skills: ['React', 'TypeScript', 'CSS'],
    min_experience: 3,
  },
];

export const demoDashboard = {
  total_candidates: 4,
  active_jobs: 2,
  interviews: 2,
  stages: {
    Applied: 1,
    Shortlisted: 1,
    Interview: 1,
    Offer: 1,
    Hired: 0,
    Rejected: 0,
  },
};

export const demoInterviews = [
  {
    id: 1,
    candidate_id: 1,
    candidate_name: 'Aarav Sharma',
    job_id: 1,
    interviewer: 'Recruiting team',
    scheduled_at: '2026-12-02T10:00:00Z',
    duration_minutes: 45,
    meeting_url: '',
    status: 'Scheduled',
  },
  {
    id: 2,
    candidate_id: 2,
    candidate_name: 'Meera Nair',
    job_id: 2,
    interviewer: 'Engineering team',
    scheduled_at: '2026-12-03T14:30:00Z',
    duration_minutes: 45,
    meeting_url: '',
    status: 'Scheduled',
  },
];

export const demoMatches = [
  {
    ...demoCandidates[0],
    score: 88,
    matched_skills: ['Python', 'FastAPI', 'PostgreSQL'],
    missing_skills: [],
    breakdown: { skills: 100, experience: 100, education: 70 },
  },
  {
    ...demoCandidates[2],
    score: 74,
    matched_skills: ['Python', 'FastAPI'],
    missing_skills: ['PostgreSQL'],
    breakdown: { skills: 67, experience: 100, education: 70 },
  },
];
