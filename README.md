# Imviz profiling

## we want to know:
- if you have a really large image loaded into imviz, at what display size does interaction become laggy
- if you have a really small image loaded into imviz with a very large display, does compression ensure that the display size doesn't matter?
- does jdaviz use local memory efficiently?
    - do copies get made or unnecessary parts of files get loaded into memory?
- how poorly does imviz performance scale with N_links (number of simultaneously loaded images)
- what CPU speed is "enough"?
    - do we benefit from being allocated >1 core?
    - (bearing in mind: EC2 allocates faster CPUs with more memory, so these will be correlated)
- how are users distributed within "nodes"/"pods"/EC2 instances, teams?
- new users would **really** benefit from guidance about which kind of server to use for a given science use-case; profiling will help us find out what's best

## performance grid dimensions
- image size
    - [(500, 1000, 10_000, 100_000) pix]^2
- viewport size
    - [(600, 1000, 2000, 4000) pix]^2
        - (with plugin tray closed)
- number of large images loaded simultaneously and WCS-linked
    - (1, 3, 5, 10, 25) images
- inside/outside of sidecar
- with and without DQ loaded
- local memory and CPU allocation
- network's download speed (python kernel to client)
    - at what download speed should we warn users that the performance will be bad / "users will experience best performance with at least X Mbps download"
    - (5, 10, 100, 1000) Mbps

## Installing
To install, check out this repository and:

    pip install -e .

Python 3.10 or later is supported (Python 3.12 or later on Windows).
