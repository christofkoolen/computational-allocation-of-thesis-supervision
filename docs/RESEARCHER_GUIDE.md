# Researcher-facing allocation guidance

## A worked example

Researchers are strongly encouraged to submit thesis topics. Submitting topics
gives you considerably more influence over the theses you will supervise.

Assume that three doctoral researchers are available as daily supervisors and
that seven students require supervision:

- Anne submitted four copyright topics;
- Lars submitted one cybersecurity topic;
- Jolien did not submit any topics;
- two additional topics were submitted by professors.

All seven topics were selected by students.

| Researcher | Expertise | Selected topics submitted | Minimum | Maximum |
| --- | --- | ---: | ---: | ---: |
| Anne | Copyright | 4 | 2 | 4 |
| Lars | Cybersecurity | 1 | 2 | 4 |
| Jolien | Artificial intelligence | 0 | 2 | 4 |

For simplicity, all three researchers are eligible and can supervise all seven
theses in the languages selected by the students.

The allocation algorithm considers all theses simultaneously. It first finds a
distribution that meets everyone's minimum workload wherever feasible. Within
that distribution, researchers receive priority for topics they submitted
themselves. Semantic matching is used for the remaining assignments.

In this example:

1. Anne receives two of her own copyright topics, satisfying her minimum.
2. Lars receives his own cybersecurity topic and one other topic selected
   through semantic matching, satisfying his minimum.
3. Jolien receives two topics submitted by other researchers or professors. The
   algorithm selects the best available semantic matches to satisfy her minimum.
4. Six assignments are needed to meet the researchers' minimums. The seventh
   goes to Anne because she submitted the topic and is also its strongest
   semantic match.

The final workload is:

| Researcher | Minimum | Maximum | Assigned |
| --- | ---: | ---: | ---: |
| Anne | 2 | 4 | 3 |
| Lars | 2 | 4 | 2 |
| Jolien | 2 | 4 | 2 |

Anne receives three of her own topics. Lars receives his own topic plus one of
the three remaining topics. Jolien receives the other two. Semantic matching
determines how Anne's fourth topic and the two professor-submitted topics are
distributed between Lars and Jolien.

The best available semantic matches may not be closely connected to a
researcher's preferred area. Jolien may, for example, receive a copyright topic
even though Anne is the stronger semantic match because Jolien must still reach
her minimum workload.

**If you submit topics and students select them, the system will try to assign
those topics to you. If you do not submit topics, you will still receive theses
to meet your minimum workload, but you will have less control over their subject
matter.**

Submitting topics does not guarantee that you will supervise all of them.
Workload requirements, eligibility, language compatibility, and maximum capacity
still apply. Submitting several relevant topics nevertheless substantially
increases your influence over the subject matter of your eventual assignments.
