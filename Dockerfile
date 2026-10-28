# The judges' site: the replay page, the narrated matches, and the tracking the generator makes
# again from each seed. It calls no model: the matches are narrated beforehand.
FROM python:3.12-slim
WORKDIR /srv
RUN pip install --no-cache-dir "numpy>=1.26" "pydantic>=2.7"
COPY sixth/ sixth/
COPY app/ app/
COPY data/ data/
ENV PORT=8000 PYTHONUNBUFFERED=1
EXPOSE 8000
USER nobody
CMD ["python", "-m", "app.server"]
