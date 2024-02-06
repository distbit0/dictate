cd /home/pimania/dev/dictation

touch ~/alex.txt
# . ~/.env

export OPENAI_API_KEY="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"
echo "1" > ~/alex.txt
python3 voice.py
echo "2" > ~/alex.txt
